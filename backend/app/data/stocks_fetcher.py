"""Stock universe ingest. Pulls OHLCV for the entire ``STOCKS`` map + the SPY
benchmark via batched ``yf.download`` and writes to ``stock_prices``. Also seeds
``instrument_metadata`` so the UI/API can read display names and sectors directly
from the database.

The batched call dramatically reduces yfinance API hits compared to one ticker at
a time: 503 names / 50 per batch = 11 HTTP fan-outs (each does threaded sub-calls
under the hood) rather than 503 sequential round trips.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Sequence

import pandas as pd
import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants_stocks import (
    BENCHMARK_TICKER,
    STOCK_INDUSTRIES,
    STOCK_SECTORS,
    STOCKS,
)
from app.core.config import get_settings
from app.db.operations import upsert_instrument_metadata, upsert_stock_prices

logger = logging.getLogger(__name__)

PRICE_LOOKBACK_DAYS = 5 * 365 + 90  # ~5 trading years + buffer for indicators warm-up
DEFAULT_BATCH_SIZE = 50


def _yf_download_batch(tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
    """Synchronous, thread-pool-friendly yfinance call for a batch."""
    return yf.download(
        tickers=list(tickers),
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        group_by="ticker",
        auto_adjust=False,
        actions=False,
        threads=True,
        progress=False,
    )


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame_to_rows(ticker: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a single-ticker OHLCV slice into upsertable rows."""
    if frame is None or frame.empty:
        return []
    sub = frame.dropna(subset=["Close"])
    rows: list[dict[str, Any]] = []
    for idx, r in sub.iterrows():
        d = pd.Timestamp(idx).date()
        close_v = _coerce_optional_float(r.get("Close"))
        if close_v is None:
            continue
        adj_v = _coerce_optional_float(r.get("Adj Close"))
        rows.append(
            {
                "ticker": ticker,
                "date": d,
                "open": _coerce_optional_float(r.get("Open")),
                "high": _coerce_optional_float(r.get("High")),
                "low": _coerce_optional_float(r.get("Low")),
                "close": close_v,
                "volume": _coerce_optional_int(r.get("Volume")),
                "adj_close": adj_v if adj_v is not None else close_v,
            }
        )
    return rows


def _panel_to_rows(panel: pd.DataFrame, requested: Sequence[str]) -> list[dict[str, Any]]:
    """Flatten yfinance's MultiIndex output (or single-ticker flat frame) into rows."""
    if panel is None or panel.empty:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(panel.columns, pd.MultiIndex):
        tickers_in_panel = list({lvl for lvl in panel.columns.get_level_values(0)})
        for ticker in tickers_in_panel:
            try:
                sub = panel[ticker]
            except KeyError:
                continue
            rows.extend(_frame_to_rows(str(ticker), sub))
    else:
        # Single-ticker request returns flat columns; ``requested`` carries the symbol.
        sole = requested[0] if len(requested) == 1 else None
        if sole:
            rows.extend(_frame_to_rows(sole, panel))
    return rows


async def seed_instrument_metadata(session: AsyncSession) -> int:
    """Upsert the stock universe metadata. Idempotent; safe to call on every refresh."""
    rows: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)
    for ticker, name in STOCKS.items():
        rows.append(
            {
                "ticker": ticker,
                "asset_class": "stock",
                "name": name,
                "sector": STOCK_SECTORS.get(ticker),
                "industry": STOCK_INDUSTRIES.get(ticker),
                "is_active": True,
                "added_at": now,
            }
        )
    rows.append(
        {
            "ticker": BENCHMARK_TICKER,
            "asset_class": "stock",
            "name": "SPDR S&P 500 ETF Trust",
            "sector": "Benchmark",
            "industry": "Index ETF",
            "is_active": True,
            "added_at": now,
        }
    )
    await upsert_instrument_metadata(session, rows)
    await session.commit()
    return len(rows)


async def ingest_stock_prices(
    session: AsyncSession,
    tickers: list[str] | None = None,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    lookback_days: int = PRICE_LOOKBACK_DAYS,
) -> dict[str, int]:
    """Pull OHLCV for the stock universe (+ benchmark) and upsert into ``stock_prices``.

    Returns counts ``{requested, rows_persisted, batches, failed_batches}``.
    """
    settings = get_settings()
    delay = float(settings.yfinance_delay_s or 1.0)

    if tickers is None:
        all_tickers = list(dict.fromkeys([*STOCKS.keys(), BENCHMARK_TICKER]))
    else:
        all_tickers = list(dict.fromkeys(tickers))

    end_d = date.today()
    start_d = end_d - timedelta(days=lookback_days)
    total_rows = 0
    batches = 0
    failed_batches = 0

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i : i + batch_size]
        batches += 1
        try:
            panel = await asyncio.to_thread(_yf_download_batch, batch, start_d, end_d)
        except Exception:  # noqa: BLE001
            logger.exception("yf.download batch %d failed (size=%d)", batches, len(batch))
            failed_batches += 1
            await asyncio.sleep(delay)
            continue

        rows = _panel_to_rows(panel, batch)
        if rows:
            try:
                await upsert_stock_prices(session, rows)
                await session.commit()
                total_rows += len(rows)
            except Exception:  # noqa: BLE001
                logger.exception("Persist batch %d failed", batches)
                failed_batches += 1
        else:
            logger.warning("Batch %d returned 0 rows for %d tickers", batches, len(batch))

        await asyncio.sleep(delay)

    logger.info(
        "ingest_stock_prices: requested=%d rows=%d batches=%d failed=%d",
        len(all_tickers),
        total_rows,
        batches,
        failed_batches,
    )
    return {
        "requested": len(all_tickers),
        "rows_persisted": total_rows,
        "batches": batches,
        "failed_batches": failed_batches,
    }
