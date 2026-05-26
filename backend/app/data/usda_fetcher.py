"""USDA PSD (Production, Supply, Distribution) data ingestion.

Free public API — no authentication required.
Endpoint: https://apps.fas.usda.gov/psdonline/api/psd/commodity/{code}/country/9000/year/{year}/
Country 9000 = World aggregate.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_BASE = "https://apps.fas.usda.gov/psdonline/api/psd"

# USDA commodity codes → ticker mapping
_COMMODITY_MAP: dict[str, str] = {
    "0440000": "ZC=F",   # Corn
    "0410000": "ZW=F",   # Wheat
    "0220000": "ZS=F",   # Soybeans
    "0711100": "KC=F",   # Coffee
    "0813100": "CT=F",   # Cotton
    "0156000": "SB=F",   # Sugar
}

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS usda_psd (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    commodity_code TEXT NOT NULL,
    attribute_id INTEGER NOT NULL,
    market_year INTEGER NOT NULL,
    value FLOAT,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, attribute_id, market_year)
);
"""


async def _ensure_table(session: AsyncSession) -> None:
    await session.execute(text(_CREATE_TABLE))
    await session.commit()


async def _fetch_commodity_year(commodity_code: str, year: int) -> list[dict]:
    url = f"{_BASE}/commodity/{commodity_code}/country/9000/year/{year}/"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.debug("USDA %s/%s returned %d", commodity_code, year, resp.status_code)
                return []
            return resp.json()
    except Exception as exc:
        logger.warning("USDA fetch failed for %s/%s: %s", commodity_code, year, exc)
        return []


async def ingest_usda(session: AsyncSession) -> dict[str, int]:
    """Fetch USDA PSD data for all mapped commodities (2020–current year).

    Returns ``{"rows_upserted": n}``.
    """
    await _ensure_table(session)

    current_year = datetime.now(tz=UTC).year
    years = list(range(2020, current_year + 1))

    total = 0
    for commodity_code, ticker in _COMMODITY_MAP.items():
        for year in years:
            rows = await _fetch_commodity_year(commodity_code, year)
            if not rows:
                continue
            for row in rows:
                attr_id = row.get("attributeId")
                value = row.get("value")
                mkt_year = row.get("marketYear") or year
                if attr_id is None:
                    continue
                try:
                    await session.execute(
                        text("""
                            INSERT INTO usda_psd (ticker, commodity_code, attribute_id, market_year, value, fetched_at)
                            VALUES (:ticker, :commodity_code, :attribute_id, :market_year, :value, NOW())
                            ON CONFLICT (ticker, attribute_id, market_year)
                            DO UPDATE SET value = EXCLUDED.value, fetched_at = NOW()
                        """),
                        {
                            "ticker": ticker,
                            "commodity_code": commodity_code,
                            "attribute_id": int(attr_id),
                            "market_year": int(mkt_year),
                            "value": float(value) if value is not None else None,
                        },
                    )
                    total += 1
                except Exception as exc:
                    logger.debug("USDA upsert failed row: %s", exc)
            await session.commit()
        logger.info("USDA ingest: %s (%s) complete", ticker, commodity_code)

    return {"rows_upserted": total}
