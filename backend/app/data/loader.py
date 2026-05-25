"""Async loaders for feature engineering."""

from __future__ import annotations

from datetime import date as _date_t
from typing import Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CommodityPrice, InstrumentMetadata, SentimentScore, StockPrice


async def load_price_ohlcv(session: AsyncSession, ticker: str) -> pd.DataFrame:
    res = await session.execute(
        select(
            CommodityPrice.date,
            CommodityPrice.open,
            CommodityPrice.high,
            CommodityPrice.low,
            CommodityPrice.close,
            CommodityPrice.volume,
            CommodityPrice.adj_close,
        )
        .where(CommodityPrice.ticker == ticker)
        .order_by(CommodityPrice.date)
    )
    rows = res.all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index().astype(float)


async def load_stock_ohlcv(session: AsyncSession, ticker: str) -> pd.DataFrame:
    """Single-ticker OHLCV from ``stock_prices`` (mirror of ``load_price_ohlcv``)."""
    res = await session.execute(
        select(
            StockPrice.date,
            StockPrice.open,
            StockPrice.high,
            StockPrice.low,
            StockPrice.close,
            StockPrice.volume,
            StockPrice.adj_close,
        )
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.date)
    )
    rows = res.all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index().astype(float)


async def load_stock_panel(
    session: AsyncSession,
    tickers: Sequence[str] | None = None,
    *,
    start: _date_t | None = None,
    end: _date_t | None = None,
) -> pd.DataFrame:
    """Long-format panel: columns = [date, ticker, open, high, low, close, volume, adj_close].

    Empty ``tickers`` means "all rows in window" — useful for one-shot training fan-out.
    """
    stmt = select(
        StockPrice.date,
        StockPrice.ticker,
        StockPrice.open,
        StockPrice.high,
        StockPrice.low,
        StockPrice.close,
        StockPrice.volume,
        StockPrice.adj_close,
    )
    if tickers:
        stmt = stmt.where(StockPrice.ticker.in_(list(tickers)))
    if start is not None:
        stmt = stmt.where(StockPrice.date >= start)
    if end is not None:
        stmt = stmt.where(StockPrice.date <= end)
    stmt = stmt.order_by(StockPrice.ticker, StockPrice.date)

    res = await session.execute(stmt)
    rows = res.all()
    if not rows:
        return pd.DataFrame(
            columns=["date", "ticker", "open", "high", "low", "close", "volume", "adj_close"]
        )
    df = pd.DataFrame(
        rows,
        columns=["date", "ticker", "open", "high", "low", "close", "volume", "adj_close"],
    )
    df["date"] = pd.to_datetime(df["date"])
    numeric_cols = ["open", "high", "low", "close", "volume", "adj_close"]
    df[numeric_cols] = df[numeric_cols].astype(float)
    return df


async def load_benchmark_series(session: AsyncSession, ticker: str = "SPY") -> pd.Series:
    """Date-indexed close series for the cross-asset benchmark."""
    res = await session.execute(
        select(StockPrice.date, StockPrice.close)
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.date)
    )
    rows = res.all()
    if not rows:
        return pd.Series(dtype=float, name=ticker)
    idx = pd.to_datetime([r[0] for r in rows])
    vals = [float(r[1]) for r in rows]
    return pd.Series(vals, index=idx, name=ticker).sort_index()


async def load_stock_oos_scores(
    session: AsyncSession,
    *,
    horizon: str = "5d",
    start: _date_t | None = None,
    end: _date_t | None = None,
) -> pd.DataFrame:
    """Long-form ``[date, ticker, score]`` from ``oos_predictions`` (the regression
    score is stored in ``y_prob`` for stocks; see ``stocks_ranker`` docstring)."""
    from app.db.models import OosPrediction

    stmt = (
        select(OosPrediction.date, OosPrediction.ticker, OosPrediction.y_prob)
        .where(
            OosPrediction.asset_class == "stock",
            OosPrediction.horizon == horizon,
            OosPrediction.ticker != "PANEL",
        )
        .order_by(OosPrediction.date, OosPrediction.ticker)
    )
    if start is not None:
        stmt = stmt.where(OosPrediction.date >= start)
    if end is not None:
        stmt = stmt.where(OosPrediction.date <= end)
    res = await session.execute(stmt)
    rows = res.all()
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "score"])
    df = pd.DataFrame(rows, columns=["date", "ticker", "score"])
    df["date"] = pd.to_datetime(df["date"])
    df["score"] = df["score"].astype(float)
    return df


async def load_stock_metadata(session: AsyncSession) -> pd.DataFrame:
    """Active stock universe metadata (ticker, name, sector, industry)."""
    res = await session.execute(
        select(
            InstrumentMetadata.ticker,
            InstrumentMetadata.name,
            InstrumentMetadata.sector,
            InstrumentMetadata.industry,
        )
        .where(InstrumentMetadata.asset_class == "stock", InstrumentMetadata.is_active.is_(True))
        .order_by(InstrumentMetadata.ticker)
    )
    rows = res.all()
    if not rows:
        return pd.DataFrame(columns=["ticker", "name", "sector", "industry"])
    return pd.DataFrame(rows, columns=["ticker", "name", "sector", "industry"])


async def load_stock_sentiment_panel(
    session: AsyncSession,
    tickers: Sequence[str] | None = None,
    *,
    start: _date_t | None = None,
    end: _date_t | None = None,
) -> pd.DataFrame:
    """Long-format sentiment ``[date, ticker, score_1d, score_3d, momentum, volume]``
    for the requested ticker set / window.

    Empty/None ``tickers`` means "all rows in window".
    """
    stmt = select(
        SentimentScore.date,
        SentimentScore.ticker,
        SentimentScore.score_1d,
        SentimentScore.score_3d,
        SentimentScore.momentum,
        SentimentScore.volume,
    )
    if tickers:
        stmt = stmt.where(SentimentScore.ticker.in_(list(tickers)))
    if start is not None:
        stmt = stmt.where(SentimentScore.date >= start)
    if end is not None:
        stmt = stmt.where(SentimentScore.date <= end)
    stmt = stmt.order_by(SentimentScore.ticker, SentimentScore.date)

    res = await session.execute(stmt)
    rows = res.all()
    cols = ["date", "ticker", "score_1d", "score_3d", "momentum", "volume"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    for c in ("score_1d", "score_3d", "momentum"):
        df[c] = df[c].astype(float)
    df["volume"] = df["volume"].fillna(0).astype(int)
    return df


async def load_sentiment_panel(session: AsyncSession, ticker: str) -> pd.DataFrame:
    res = await session.execute(
        select(
            SentimentScore.date,
            SentimentScore.score_1d,
            SentimentScore.score_3d,
            SentimentScore.volume,
            SentimentScore.momentum,
        )
        .where(SentimentScore.ticker == ticker)
        .order_by(SentimentScore.date)
    )
    rows = res.all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "score_1d", "score_3d", "volume", "momentum"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index().astype(float)
