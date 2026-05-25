"""PostgreSQL UPSERT helpers and bulk inserts."""
from datetime import date, datetime  # noqa: F401 — used in type hints in callers
from typing import Any, Iterable, Iterator, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BacktestResult,
    CommodityPrice,
    InstrumentMetadata,
    MacroIndicator,
    ModelHyperparam,
    ModelRun,
    OosPrediction,
    PortfolioEquity,
    PortfolioHolding,
    PortfolioRanking,
    SentimentScore,
    Signal,
    StockPrice,
)


# Postgres bind-parameter limit per statement is 32767. We size each bulk
# write so ``rows_per_batch * cols_per_row`` stays below this bound with a
# safety margin (~30000). One ingest of 5y of S&P 500 OHLCV is well over a
# million parameters, so this matters everywhere a ``Sequence[dict]`` is
# inserted.
_PG_PARAM_BUDGET = 30_000


def _chunked(rows: Sequence[dict[str, Any]]) -> Iterator[Sequence[dict[str, Any]]]:
    """Yield slices of ``rows`` sized to keep each INSERT under the Postgres
    bind-parameter limit. Rows are assumed homogeneous; the first row's key
    count is taken as ``cols_per_row``."""
    if not rows:
        return
    cols = max(1, len(rows[0]))
    batch = max(1, _PG_PARAM_BUDGET // cols)
    for i in range(0, len(rows), batch):
        yield rows[i : i + batch]


async def upsert_commodity_prices(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(CommodityPrice).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_commodity_price_ticker_date",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "adj_close": stmt.excluded.adj_close,
            },
        )
        await session.execute(stmt)


async def upsert_macro(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(MacroIndicator).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MacroIndicator.date.key],
            set_={
                "fed_funds_rate": stmt.excluded.fed_funds_rate,
                "usd_eur": stmt.excluded.usd_eur,
                "usd_jpy": stmt.excluded.usd_jpy,
                "yield_spread_10y2y": stmt.excluded.yield_spread_10y2y,
                "breakeven_inflation": stmt.excluded.breakeven_inflation,
                "vix": stmt.excluded.vix,
                "cpi_yoy": stmt.excluded.cpi_yoy,
                "wti_spot": stmt.excluded.wti_spot,
                "gold_fix": stmt.excluded.gold_fix,
                "unrate": stmt.excluded.unrate,
            },
        )
        await session.execute(stmt)


async def upsert_sentiment(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(SentimentScore).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_sentiment_ticker_date",
            set_={
                "score_1d": stmt.excluded.score_1d,
                "score_3d": stmt.excluded.score_3d,
                "volume": stmt.excluded.volume,
                "momentum": stmt.excluded.momentum,
            },
        )
        await session.execute(stmt)


async def bulk_insert_signals(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        await session.execute(pg_insert(Signal).values(batch))


async def insert_model_runs(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        await session.execute(pg_insert(ModelRun).values(batch))


async def replace_oos_predictions(
    session: AsyncSession,
    ticker: str,
    horizon: str,
    rows: Sequence[dict[str, Any]],
) -> None:
    await session.execute(delete(OosPrediction).where(OosPrediction.ticker == ticker, OosPrediction.horizon == horizon))
    for batch in _chunked(rows):
        await session.execute(pg_insert(OosPrediction).values(batch))


async def insert_oos_predictions(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(OosPrediction).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_oos_pred",
            set_={"y_prob": stmt.excluded.y_prob, "y_true": stmt.excluded.y_true},
        )
        await session.execute(stmt)


async def insert_backtests(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        await session.execute(pg_insert(BacktestResult).values(batch))


async def delete_backtests_for_tickers(session: AsyncSession, tickers: Sequence[str]) -> None:
    if not tickers:
        return
    await session.execute(delete(BacktestResult).where(BacktestResult.ticker.in_(list(tickers))))


async def upsert_hyperparams(session: AsyncSession, row: dict[str, Any]) -> None:
    stmt = pg_insert(ModelHyperparam).values(**row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_model_hyperparams",
        set_={"params_json": stmt.excluded.params_json, "tuned_at": stmt.excluded.tuned_at},
    )
    await session.execute(stmt)


async def fetch_latest_closes(session: AsyncSession, tickers: Sequence[str]) -> dict[str, float]:
    if not tickers:
        return {}
    sub = (
        select(CommodityPrice.ticker, func.max(CommodityPrice.date).label("md"))
        .where(CommodityPrice.ticker.in_(list(tickers)))
        .group_by(CommodityPrice.ticker)
        .subquery()
    )
    q = (
        select(CommodityPrice.ticker, CommodityPrice.close)
        .join(sub, (CommodityPrice.ticker == sub.c.ticker) & (CommodityPrice.date == sub.c.md))
        .where(CommodityPrice.ticker.in_(list(tickers)))
    )
    rows = await session.execute(q)
    out: dict[str, float] = {}
    for tkr, clo in rows.all():
        if clo is not None:
            out[str(tkr)] = float(clo)
    return out


async def upsert_stock_prices(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(StockPrice).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stock_price_ticker_date",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "adj_close": stmt.excluded.adj_close,
            },
        )
        await session.execute(stmt)


async def upsert_instrument_metadata(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(InstrumentMetadata).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_instrument_ticker_class",
            set_={
                "name": stmt.excluded.name,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "is_active": stmt.excluded.is_active,
            },
        )
        await session.execute(stmt)


async def upsert_portfolio_rankings(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(PortfolioRanking).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ranking_date_ticker_horizon",
            set_={
                "score": stmt.excluded.score,
                "rank": stmt.excluded.rank,
                "sector": stmt.excluded.sector,
                "in_topk": stmt.excluded.in_topk,
                "generated_at": stmt.excluded.generated_at,
            },
        )
        await session.execute(stmt)


async def upsert_portfolio_holdings(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(PortfolioHolding).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_holding_date_ticker",
            set_={
                "weight": stmt.excluded.weight,
                "entry_price": stmt.excluded.entry_price,
                "last_price": stmt.excluded.last_price,
                "sector": stmt.excluded.sector,
            },
        )
        await session.execute(stmt)


async def upsert_portfolio_equity(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    for batch in _chunked(rows):
        stmt = pg_insert(PortfolioEquity).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_portfolio_equity_date",
            set_={
                "equity": stmt.excluded.equity,
                "benchmark_equity": stmt.excluded.benchmark_equity,
                "daily_return": stmt.excluded.daily_return,
                "turnover": stmt.excluded.turnover,
            },
        )
        await session.execute(stmt)


async def fetch_latest_stock_closes(session: AsyncSession, tickers: Sequence[str]) -> dict[str, float]:
    if not tickers:
        return {}
    sub = (
        select(StockPrice.ticker, func.max(StockPrice.date).label("md"))
        .where(StockPrice.ticker.in_(list(tickers)))
        .group_by(StockPrice.ticker)
        .subquery()
    )
    q = (
        select(StockPrice.ticker, StockPrice.close)
        .join(sub, (StockPrice.ticker == sub.c.ticker) & (StockPrice.date == sub.c.md))
        .where(StockPrice.ticker.in_(list(tickers)))
    )
    rows = await session.execute(q)
    out: dict[str, float] = {}
    for tkr, clo in rows.all():
        if clo is not None:
            out[str(tkr)] = float(clo)
    return out


async def load_close_history(
    session: AsyncSession,
    tickers: Sequence[str],
    lookback_days: int = 400,
) -> dict[str, list[tuple[Any, Any]]]:
    """Load recent (date, close) per ticker ascending."""
    from datetime import timedelta

    cutoff = await session.scalar(select(func.max(CommodityPrice.date)))
    if cutoff is None:
        return {t: [] for t in tickers}
    start = cutoff - timedelta(days=int(lookback_days * 1.5))

    rows = await session.execute(
        select(CommodityPrice.ticker, CommodityPrice.date, CommodityPrice.close)
        .where(CommodityPrice.ticker.in_(list(tickers)), CommodityPrice.date >= start)
        .order_by(CommodityPrice.ticker, CommodityPrice.date)
    )
    out: dict[str, list[tuple[Any, Any]]] = {str(t): [] for t in tickers}
    for tkr, dt, clo in rows.all():
        if clo is None:
            continue
        out.setdefault(str(tkr), []).append((dt, float(clo)))
    return out
