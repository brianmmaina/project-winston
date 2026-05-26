"""CFTC Commitment of Traders (disaggregated) weekly data fetcher.

Downloads the current-year disaggregated COT CSV from the CFTC website.
No API key required — data is public domain.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CotReport

logger = logging.getLogger(__name__)

# Disaggregated futures-only COT — all years use the same ZIP naming
_COT_URL_HIST_TMPL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

# Map CFTC market name substrings → our ticker
_MARKET_MAP: dict[str, str] = {
    "CRUDE OIL": "CL=F",
    "NATURAL GAS": "NG=F",
    "HEATING OIL": "HO=F",
    "RBOB GASOLINE": "RB=F",
    "BRENT CRUDE": "BZ=F",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "COPPER": "HG=F",
    "PLATINUM": "PL=F",
    "PALLADIUM": "PA=F",
    "CORN": "ZC=F",
    "WHEAT-SRW": "ZW=F",
    "SOYBEANS": "ZS=F",
    "COFFEE C": "KC=F",
    "COTTON NO. 2": "CT=F",
    "SUGAR NO. 11": "SB=F",
    "COCOA": "CC=F",
}

_COT_COLS = {
    "Market_and_Exchange_Names": "market",
    "Report_Date_as_YYYY-MM-DD": "report_date",
    "Open_Interest_All": "open_interest",
    "Prod_Merc_Positions_Long_All": "comm_long",
    "Prod_Merc_Positions_Short_All": "comm_short",
    "M_Money_Positions_Long_All": "spec_long",
    "M_Money_Positions_Short_All": "spec_short",
}


def _match_ticker(market_name: str) -> str | None:
    upper = market_name.upper()
    for key, ticker in _MARKET_MAP.items():
        if key in upper:
            return ticker
    return None


def _parse_cot_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    available = {c: c for c in df.columns}
    rename = {k: v for k, v in _COT_COLS.items() if k in available}
    df = df.rename(columns=rename)
    needed = list(_COT_COLS.values())
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"COT CSV missing columns: {missing}")
    df = df[needed].copy()
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
    df = df.dropna(subset=["report_date"])
    for col in ["open_interest", "comm_long", "comm_short", "spec_long", "spec_short"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    df["ticker"] = df["market"].apply(_match_ticker)
    df = df.dropna(subset=["ticker"])
    df["comm_net"] = df["comm_long"] - df["comm_short"]
    df["spec_net"] = df["spec_long"] - df["spec_short"]
    df["spec_pct_long"] = df["spec_long"] / (df["spec_long"] + df["spec_short"]).replace(0, float("nan"))
    # Multiple exchanges can map to the same ticker — keep highest open_interest per (ticker, date)
    df = df.sort_values("open_interest", ascending=False).drop_duplicates(subset=["ticker", "report_date"])
    return df


async def _fetch_raw(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def ingest_cot_data(session: AsyncSession, years_back: int = 3) -> int:
    """Download and upsert COT data. Returns number of rows inserted/updated."""
    rows_total = 0
    current_year = date.today().year

    # All years including current use the same ZIP naming
    import zipfile
    for yr in range(current_year - years_back, current_year + 1):
        url = _COT_URL_HIST_TMPL.format(year=yr)
        try:
            raw_zip = await _fetch_raw(url)
            zf = zipfile.ZipFile(io.BytesIO(raw_zip))
            csv_name = next(n for n in zf.namelist() if n.endswith(".txt") or n.endswith(".csv"))
            raw = zf.read(csv_name)
            df = _parse_cot_csv(raw)
            n = await _upsert_cot_df(session, df)
            await session.commit()
            rows_total += n
            logger.info("COT %d: %d rows upserted", yr, n)
        except Exception as exc:
            await session.rollback()
            logger.warning("COT %d failed: %s", yr, exc)

    return rows_total


async def _upsert_cot_df(session: AsyncSession, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        records.append({
            "ticker": str(row["ticker"]),
            "report_date": row["report_date"],
            "open_interest": int(row["open_interest"]) if pd.notna(row["open_interest"]) else None,
            "comm_long": int(row["comm_long"]) if pd.notna(row["comm_long"]) else None,
            "comm_short": int(row["comm_short"]) if pd.notna(row["comm_short"]) else None,
            "spec_long": int(row["spec_long"]) if pd.notna(row["spec_long"]) else None,
            "spec_short": int(row["spec_short"]) if pd.notna(row["spec_short"]) else None,
            "comm_net": int(row["comm_net"]) if pd.notna(row["comm_net"]) else None,
            "spec_net": int(row["spec_net"]) if pd.notna(row["spec_net"]) else None,
            "spec_pct_long": float(row["spec_pct_long"]) if pd.notna(row["spec_pct_long"]) else None,
        })
    if not records:
        return 0
    stmt = insert(CotReport).values(records)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_cot_ticker_date",
        set_={
            "open_interest": stmt.excluded.open_interest,
            "comm_long": stmt.excluded.comm_long,
            "comm_short": stmt.excluded.comm_short,
            "spec_long": stmt.excluded.spec_long,
            "spec_short": stmt.excluded.spec_short,
            "comm_net": stmt.excluded.comm_net,
            "spec_net": stmt.excluded.spec_net,
            "spec_pct_long": stmt.excluded.spec_pct_long,
        },
    )
    await session.execute(stmt)
    return len(records)


async def get_latest_cot(session: AsyncSession, ticker: str) -> dict[str, Any] | None:
    from sqlalchemy import select, desc
    q = await session.execute(
        select(CotReport)
        .where(CotReport.ticker == ticker)
        .order_by(desc(CotReport.report_date))
        .limit(1)
    )
    row = q.scalars().first()
    if row is None:
        return None
    return {
        "report_date": row.report_date.isoformat(),
        "open_interest": row.open_interest,
        "comm_net": row.comm_net,
        "spec_net": row.spec_net,
        "spec_pct_long": float(row.spec_pct_long) if row.spec_pct_long is not None else None,
    }


async def get_cot_history(session: AsyncSession, ticker: str, weeks: int = 52) -> list[dict[str, Any]]:
    from sqlalchemy import select, desc
    cutoff = date.today() - timedelta(weeks=weeks)
    q = await session.execute(
        select(CotReport)
        .where(CotReport.ticker == ticker, CotReport.report_date >= cutoff)
        .order_by(CotReport.report_date)
    )
    rows = q.scalars().all()
    return [
        {
            "report_date": r.report_date.isoformat(),
            "comm_net": r.comm_net,
            "spec_net": r.spec_net,
            "spec_pct_long": float(r.spec_pct_long) if r.spec_pct_long is not None else None,
            "open_interest": r.open_interest,
        }
        for r in rows
    ]
