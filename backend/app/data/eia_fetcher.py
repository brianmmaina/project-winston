"""EIA weekly petroleum and natural gas inventory fetcher.

Uses EIA Open Data API v2 (free, requires EIA_API_KEY from eia.gov/opendata).
Key series: crude oil stocks, nat gas storage, distillate/gasoline inventories.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import EiaInventory

logger = logging.getLogger(__name__)

_EIA_BASE = "https://api.eia.gov/v2"

# Series ID → (ticker, units, description)
_EIA_SERIES: dict[str, tuple[str, str, str]] = {
    # Crude oil stocks (weekly, MBBL)
    "PET.WCRSTUS1.W": ("CL=F", "MBBL", "US Crude Oil Stocks excl. SPR"),
    # Crude oil imports
    "PET.WCRIMUS2.W": ("CL=F", "MBBL/D", "US Crude Oil Imports"),
    # Natural gas storage (weekly, BCF)
    "NG.NW2_EPG0_SWO_R48_BCF.W": ("NG=F", "BCF", "US Natural Gas in Underground Storage"),
    # Distillate stocks (heating oil)
    "PET.WDISTUS1.W": ("HO=F", "MBBL", "US Distillate Fuel Stocks"),
    # RBOB/gasoline stocks
    "PET.WGFUPUS2.W": ("RB=F", "MBBL", "US Gasoline Stocks"),
}


async def _fetch_series(api_key: str, series_id: str, start: date) -> list[dict[str, Any]]:
    """Fetch one EIA series. Returns list of {date, value} dicts."""
    # EIA v2 route: /seriesid/{series_id}
    url = f"{_EIA_BASE}/seriesid/{series_id}"
    params = {
        "api_key": api_key,
        "start": start.isoformat(),
        "out": "json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    data = payload.get("response", {}).get("data", [])
    results = []
    for item in data:
        raw_date = item.get("period") or item.get("date")
        val = item.get("value")
        if raw_date and val is not None:
            try:
                results.append({"date": pd.to_datetime(raw_date).date(), "value": float(val)})
            except Exception:
                pass
    return sorted(results, key=lambda x: x["date"])


async def ingest_eia_data(session: AsyncSession, weeks_back: int = 260) -> int:
    settings = get_settings()
    api_key = (settings.eia_api_key or "").strip()
    if not api_key:
        logger.warning("EIA_API_KEY not configured — skipping EIA inventory ingestion")
        return 0

    start = date.today() - timedelta(weeks=weeks_back)
    total = 0

    for series_id, (ticker, units, _desc) in _EIA_SERIES.items():
        try:
            points = await _fetch_series(api_key, series_id, start)
            if not points:
                continue

            records: list[dict[str, Any]] = []
            prev_val: float | None = None
            for pt in points:
                wow = (pt["value"] - prev_val) if prev_val is not None else None
                records.append({
                    "series_id": series_id,
                    "ticker": ticker,
                    "report_date": pt["date"],
                    "value": pt["value"],
                    "units": units,
                    "wow_change": wow,
                })
                prev_val = pt["value"]

            stmt = insert(EiaInventory).values(records)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_eia_series_date",
                set_={"value": stmt.excluded.value, "wow_change": stmt.excluded.wow_change},
            )
            await session.execute(stmt)
            total += len(records)
            logger.info("EIA %s: %d rows upserted", series_id, len(records))
        except Exception as exc:
            logger.warning("EIA series %s failed: %s", series_id, exc)

    await session.commit()
    return total


async def get_latest_eia(session: AsyncSession, ticker: str) -> list[dict[str, Any]]:
    from sqlalchemy import select, desc
    q = await session.execute(
        select(EiaInventory)
        .where(EiaInventory.ticker == ticker)
        .order_by(desc(EiaInventory.report_date))
        .limit(10)
    )
    rows = q.scalars().all()
    return [
        {
            "series_id": r.series_id,
            "report_date": r.report_date.isoformat(),
            "value": float(r.value) if r.value is not None else None,
            "units": r.units,
            "wow_change": float(r.wow_change) if r.wow_change is not None else None,
        }
        for r in rows
    ]
