"""Price & macro ingestion (yfinance + FRED)."""
import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from fredapi import Fred
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COMMODITIES, FRED_SERIES
from app.core.config import get_settings
from app.db.models import MacroIndicator
from app.db.operations import upsert_commodity_prices, upsert_macro

logger = logging.getLogger(__name__)

PRICE_LOOKBACK_DAYS = 7 * 365 + 180


def fetch_yfinance_prices_sync(ticker: str, start: date, end: date) -> pd.DataFrame:
    tkr = yf.Ticker(ticker)
    hist = tkr.history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=False,
    )
    if hist is None or hist.empty:
        logger.warning("yfinance returned empty OHLC for %s", ticker)
        return pd.DataFrame()

    tzname = getattr(hist.index, "tz", None)
    if tzname is not None:
        hist.index = hist.index.tz_convert(None)

    close = hist.get("Close")
    adj = hist.get("Adj Close", close)

    df = pd.DataFrame(
        {
            "open": hist.get("Open"),
            "high": hist.get("High"),
            "low": hist.get("Low"),
            "close": close,
            "volume": hist.get("Volume"),
            "adj_close": adj,
        },
        index=hist.index,
    ).sort_index()

    df = df.dropna(subset=["close"])
    return df.astype(float)


async def ingest_commodity_prices(session: AsyncSession) -> int:
    settings = get_settings()
    delay = float(settings.yfinance_delay_s or 1.0)
    end_d = date.today()
    start_d = end_d - timedelta(days=PRICE_LOOKBACK_DAYS)
    total = 0
    rows_batch: list[dict[str, Any]] = []

    for ticker in COMMODITIES.keys():
        try:
            df = await asyncio.to_thread(fetch_yfinance_prices_sync, ticker, start_d, end_d)
        except Exception as exc:  # noqa: BLE001
            logger.exception("fetch %s failed: %s", ticker, exc)
            await asyncio.sleep(delay)
            continue

        for dt_index, row in df.iterrows():
            d = pd.Timestamp(dt_index).date()
            rv = row.to_dict()
            vol = rv.get("volume")
            rows_batch.append(
                {
                    "ticker": ticker,
                    "date": d,
                    "open": float(rv["open"]),
                    "high": float(rv["high"]),
                    "low": float(rv["low"]),
                    "close": float(rv["close"]),
                    "volume": None if pd.isna(vol) else int(vol),
                    "adj_close": (
                        float(rv["adj_close"])
                        if not pd.isna(rv.get("adj_close"))
                        else float(rv["close"])
                    ),
                }
            )
            total += 1

        if len(rows_batch) >= 2500:
            await upsert_commodity_prices(session, rows_batch)
            rows_batch.clear()
            await session.commit()

        await asyncio.sleep(delay)

    if rows_batch:
        await upsert_commodity_prices(session, rows_batch)
        await session.commit()

    logger.info("ingest_commodity_prices rows=%s", total)
    return total


def _fred_df_sync(api_key: str) -> pd.DataFrame:
    fred = Fred(api_key=api_key)
    series_map: dict[str, pd.Series] = {}
    for col, sid in FRED_SERIES.items():
        try:
            ser = fred.get_series(sid).astype(float).sort_index()

            dt_idx = pd.DatetimeIndex(pd.to_datetime(ser.index, utc=False))
            if getattr(dt_idx, "tz", None) is not None:
                dt_idx = dt_idx.tz_convert(None)
            ser.index = dt_idx.normalize()
            series_map[col] = ser
        except Exception as exc:  # noqa: BLE001
            logger.warning("FRED fetch %s (%s): %s", sid, col, exc)

    if not series_map:
        raise RuntimeError("No FRED series downloaded — check API key / network.")

    merged = pd.DataFrame(series_map).sort_index()
    merged.index = pd.to_datetime(pd.Index(merged.index)).normalize()
    daily = pd.date_range(merged.index.min(), merged.index.max(), freq="D")
    merged = merged.reindex(daily).ffill()

    if "cpi" in merged.columns:
        cpi = merged["cpi"].astype(float)
        merged["cpi_yoy"] = (cpi / cpi.shift(12) - 1.0) * 100.0

    cols_want = (
        "fed_funds_rate",
        "usd_eur",
        "usd_jpy",
        "yield_spread_10y2y",
        "breakeven_inflation",
        "vix",
        "cpi_yoy",
        "wti_spot",
        "gold_fix",
        "unrate",
    )

    return merged[[c for c in cols_want if c in merged.columns]].ffill()


async def ingest_macro_indicators(session: AsyncSession) -> int:
    settings = get_settings()
    key = (settings.fred_api_key or "").strip()
    if not key:
        logger.warning("FRED_API_KEY missing — skipping macro ingestion")
        return 0

    macro = await asyncio.to_thread(_fred_df_sync, key)

    rows: list[dict[str, Any]] = []
    cols_final = (
        "fed_funds_rate",
        "usd_eur",
        "usd_jpy",
        "yield_spread_10y2y",
        "breakeven_inflation",
        "vix",
        "cpi_yoy",
        "wti_spot",
        "gold_fix",
        "unrate",
    )

    for dt_idx, vals in macro.iterrows():
        d = pd.Timestamp(dt_idx).date()
        rec: dict[str, Any] = {"date": d}
        for col in cols_final:
            if col not in macro.columns:
                rec[col] = None
                continue
            vv = vals[col]
            if vv is None or (isinstance(vv, float) and (vv != vv)):
                rec[col] = None
            else:
                rec[col] = float(vv)
        rows.append(rec)

    await upsert_macro(session, rows)
    await session.commit()
    logger.info("ingest_macro_indicators rows=%s", len(rows))
    return len(rows)


async def load_macro_dataframe(session: AsyncSession) -> pd.DataFrame:
    res = await session.execute(select(MacroIndicator))
    objs = list(res.scalars().all())
    if not objs:
        return pd.DataFrame()
    cols = ["date"] + [
        str(c.key) for c in MacroIndicator.__mapper__.columns if str(c.key) != "date"
    ]

    raw = []
    for r in objs:
        raw.append({c: getattr(r, c, None) for c in cols})

    df = pd.DataFrame(raw)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    df.index.name = None
    return df
