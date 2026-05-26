"""Earnings calendar and economic event calendar fetchers.

Earnings: persisted from yfinance for active S&P 500 stocks.
Economic: FOMC, CPI, NFP, PCE dates from hardcoded Fed/BLS schedule + FRED.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EarningsEvent, EconomicEvent

logger = logging.getLogger(__name__)

# Known 2025-2026 FOMC meeting dates (end-of-meeting day, rate decision)
_FOMC_DATES_2025_2026 = [
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7),
    date(2025, 6, 18), date(2025, 7, 30), date(2025, 9, 17),
    date(2025, 10, 29), date(2025, 12, 10),
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
    date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
    date(2026, 10, 28), date(2026, 12, 9),
]

# CPI release schedule 2025-2026 (approximate — BLS releases mid-month)
_CPI_DATES_2025_2026 = [
    date(2025, 1, 15), date(2025, 2, 12), date(2025, 3, 12),
    date(2025, 4, 10), date(2025, 5, 13), date(2025, 6, 11),
    date(2025, 7, 11), date(2025, 8, 12), date(2025, 9, 10),
    date(2025, 10, 15), date(2025, 11, 13), date(2025, 12, 10),
    date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 11),
    date(2026, 4, 9),  date(2026, 5, 13), date(2026, 6, 10),
    date(2026, 7, 10), date(2026, 8, 12), date(2026, 9, 9),
    date(2026, 10, 14), date(2026, 11, 12), date(2026, 12, 9),
]

# NFP (Non-Farm Payrolls) — first Friday of each month
_NFP_DATES_2025_2026 = [
    date(2025, 1, 10), date(2025, 2, 7),  date(2025, 3, 7),
    date(2025, 4, 4),  date(2025, 5, 2),  date(2025, 6, 6),
    date(2025, 7, 3),  date(2025, 8, 1),  date(2025, 9, 5),
    date(2025, 10, 3), date(2025, 11, 7), date(2025, 12, 5),
    date(2026, 1, 9),  date(2026, 2, 6),  date(2026, 3, 6),
    date(2026, 4, 3),  date(2026, 5, 1),  date(2026, 6, 5),
    date(2026, 7, 2),  date(2026, 8, 7),  date(2026, 9, 4),
    date(2026, 10, 2), date(2026, 11, 6), date(2026, 12, 4),
]


async def ingest_economic_calendar(session: AsyncSession) -> int:
    """Upsert hardcoded FOMC, CPI, NFP events."""
    records: list[dict[str, Any]] = []

    for d in _FOMC_DATES_2025_2026:
        records.append({"event_type": "FOMC", "event_date": d,
                        "description": "FOMC rate decision", "impact": "high"})
    for d in _CPI_DATES_2025_2026:
        records.append({"event_type": "CPI", "event_date": d,
                        "description": "Consumer Price Index release", "impact": "high"})
    for d in _NFP_DATES_2025_2026:
        records.append({"event_type": "NFP", "event_date": d,
                        "description": "Non-Farm Payrolls release", "impact": "high"})

    if not records:
        return 0

    stmt = insert(EconomicEvent).values(records)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_econ_type_date",
        set_={"description": stmt.excluded.description, "impact": stmt.excluded.impact},
    )
    await session.execute(stmt)
    await session.commit()
    return len(records)


def _fetch_earnings_sync(ticker: str) -> list[dict[str, Any]]:
    try:
        tkr = yf.Ticker(ticker)
        cal = tkr.calendar
        if cal is None or cal.empty:
            return []
        results = []
        for col in cal.columns:
            row = cal[col]
            earnings_date_raw = row.get("Earnings Date")
            if earnings_date_raw is None:
                continue
            try:
                earnings_date = pd.to_datetime(earnings_date_raw).date()
            except Exception:
                continue
            eps_est = row.get("EPS Estimate")
            rev_est = row.get("Revenue Estimate")
            results.append({
                "ticker": ticker,
                "earnings_date": earnings_date,
                "timing": None,
                "eps_estimate": float(eps_est) if pd.notna(eps_est) else None,
                "eps_actual": None,
                "revenue_estimate": float(rev_est) if pd.notna(rev_est) else None,
                "revenue_actual": None,
                "surprise_pct": None,
            })
        return results
    except Exception as exc:
        logger.debug("yfinance earnings for %s: %s", ticker, exc)
        return []


async def ingest_earnings_calendar(session: AsyncSession, tickers: list[str], delay_s: float = 0.5) -> int:
    """Fetch and persist upcoming earnings dates for a list of tickers."""
    total = 0
    for ticker in tickers:
        records = await asyncio.to_thread(_fetch_earnings_sync, ticker)
        if not records:
            await asyncio.sleep(delay_s)
            continue
        stmt = insert(EarningsEvent).values(records)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_earnings_ticker_date",
            set_={
                "eps_estimate": stmt.excluded.eps_estimate,
                "revenue_estimate": stmt.excluded.revenue_estimate,
            },
        )
        await session.execute(stmt)
        total += len(records)
        await asyncio.sleep(delay_s)

    await session.commit()
    logger.info("Earnings calendar: %d rows upserted for %d tickers", total, len(tickers))
    return total


async def get_upcoming_earnings(session: AsyncSession, days: int = 14) -> list[dict[str, Any]]:
    from sqlalchemy import select
    cutoff = date.today() + timedelta(days=days)
    q = await session.execute(
        select(EarningsEvent)
        .where(EarningsEvent.earnings_date >= date.today(), EarningsEvent.earnings_date <= cutoff)
        .order_by(EarningsEvent.earnings_date)
    )
    rows = q.scalars().all()
    return [
        {
            "ticker": r.ticker,
            "earnings_date": r.earnings_date.isoformat(),
            "timing": r.timing,
            "eps_estimate": float(r.eps_estimate) if r.eps_estimate is not None else None,
        }
        for r in rows
    ]


async def get_upcoming_economic_events(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    from sqlalchemy import select
    cutoff = date.today() + timedelta(days=days)
    q = await session.execute(
        select(EconomicEvent)
        .where(EconomicEvent.event_date >= date.today(), EconomicEvent.event_date <= cutoff)
        .order_by(EconomicEvent.event_date)
    )
    rows = q.scalars().all()
    return [
        {
            "event_type": r.event_type,
            "event_date": r.event_date.isoformat(),
            "description": r.description,
            "impact": r.impact,
            "forecast_value": float(r.forecast_value) if r.forecast_value is not None else None,
            "actual_value": float(r.actual_value) if r.actual_value is not None else None,
        }
        for r in rows
    ]
