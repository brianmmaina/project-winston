"""``/api/stocks/*`` router — universe, rankings, portfolio, backtest, model
stats, and async refresh/retrain. Mounted in ``app.main`` via
``app.include_router(stocks_router)``.

Read endpoints query the DB directly; write endpoints (``refresh`` / ``retrain``)
spawn background tasks and return a job id so the UI can poll. The background
task updates a row in the ``job_status`` table.
"""

from __future__ import annotations

import logging
from datetime import UTC, date as date_t, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.constants_stocks import (
    BENCHMARK_TICKER,
    STOCK_INDUSTRIES,
    STOCK_SECTORS,
    STOCKS,
)
from app.core.security import require_api_key
from app.data.loader import (
    load_stock_metadata,
)
from app.db.models import (
    BacktestResult,
    InstrumentMetadata,
    ModelRun,
    PortfolioEquity,
    PortfolioHolding,
    PortfolioRanking,
    StockPrice,
)
from app.db.operations import fetch_latest_stock_closes
from app.db.session import async_session_factory
from app.services.jobs_service import (
    complete_job,
    fail_job,
    mark_running,
    start_job,
)
from app.services.stocks_service import (
    refresh_stocks_data,
    run_daily_ranking,
    run_portfolio_backtest,
    train_stocks_panel,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


# ----------------------------------------------------------------------------
# Universe + metadata
# ----------------------------------------------------------------------------


class UniverseRow(BaseModel):
    ticker: str
    name: str
    sector: str | None
    industry: str | None
    last_close: float | None


@router.get("/universe", response_model=list[UniverseRow])
async def api_stock_universe(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    meta_df = await load_stock_metadata(session)
    if meta_df.empty:
        rows = [
            {
                "ticker": t,
                "name": n,
                "sector": STOCK_SECTORS.get(t),
                "industry": STOCK_INDUSTRIES.get(t),
            }
            for t, n in STOCKS.items()
        ]
    else:
        rows = meta_df.to_dict("records")  # type: ignore[assignment]

    tickers = [r["ticker"] for r in rows]
    last_close = await fetch_latest_stock_closes(session, tickers)

    out: list[dict[str, Any]] = []
    for r in rows:
        ticker = str(r["ticker"])
        out.append(
            {
                "ticker": ticker,
                "name": str(r["name"]),
                "sector": r.get("sector"),
                "industry": r.get("industry"),
                "last_close": float(last_close[ticker]) if ticker in last_close else None,
            }
        )
    return out


# ----------------------------------------------------------------------------
# Rankings / portfolio
# ----------------------------------------------------------------------------


class RankingRow(BaseModel):
    date: date_t
    ticker: str
    name: str | None = None
    sector: str | None = None
    score: float
    rank: int
    in_topk: bool
    horizon: str
    last_close: float | None = None
    momentum_score: float | None = None
    quality_score: float | None = None
    value_score: float | None = None


def _zscore_series(vals: dict[str, float]) -> dict[str, float]:
    """Cross-sectional z-score a dict of ticker → value."""
    if not vals:
        return {}
    import statistics
    v_list = list(vals.values())
    if len(v_list) < 2:
        return {k: 0.0 for k in vals}
    mu = statistics.mean(v_list)
    sd = statistics.stdev(v_list) or 1.0
    return {k: round((v - mu) / sd, 4) for k, v in vals.items()}


async def _compute_factor_scores(session: AsyncSession, tickers: list[str]) -> dict[str, dict[str, float]]:
    """Batch-compute momentum, quality, value z-scores cross-sectionally."""
    if not tickers:
        return {}
    cutoff = date_t.today() - timedelta(days=280)
    q = await session.execute(
        select(StockPrice.ticker, StockPrice.date, StockPrice.close)
        .where(StockPrice.ticker.in_(tickers), StockPrice.date >= cutoff, StockPrice.close.isnot(None))
        .order_by(StockPrice.ticker, StockPrice.date)
    )
    rows = q.all()
    # Group by ticker
    from collections import defaultdict
    price_map: dict[str, list[tuple[date_t, float]]] = defaultdict(list)
    for row in rows:
        price_map[row[0]].append((row[1], float(row[2])))

    raw_mom: dict[str, float] = {}
    raw_qual: dict[str, float] = {}
    raw_val: dict[str, float] = {}

    for ticker, pairs in price_map.items():
        if len(pairs) < 22:
            continue
        closes = [p for _, p in pairs]
        latest = closes[-1]
        # Momentum: 12-1m return (last 252 days minus last 21 days)
        p252 = closes[0] if len(closes) >= 252 else closes[0]
        p21 = closes[-22] if len(closes) >= 22 else closes[0]
        raw_mom[ticker] = (p21 / p252 - 1.0) if p252 > 0 else 0.0
        # Quality: negative annualised volatility (lower vol = higher quality)
        if len(closes) >= 22:
            import math
            rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, min(63, len(closes)))]
            std = (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / len(rets)) ** 0.5
            raw_qual[ticker] = -(std * math.sqrt(252))
        # Value: inverse proximity to 52w high (lower proximity = higher value)
        high_52w = max(c for _, c in pairs[-252:]) if len(pairs) >= 252 else max(c for _, c in pairs)
        raw_val[ticker] = 1.0 - (latest / high_52w) if high_52w > 0 else 0.0

    mom_z = _zscore_series(raw_mom)
    qual_z = _zscore_series(raw_qual)
    val_z = _zscore_series(raw_val)

    result: dict[str, dict[str, float]] = {}
    for ticker in tickers:
        result[ticker] = {
            "momentum_score": mom_z.get(ticker),
            "quality_score": qual_z.get(ticker),
            "value_score": val_z.get(ticker),
        }
    return result


@router.get("/rankings", response_model=list[RankingRow])
async def api_stock_rankings(
    horizon: str = Query("5d"),
    top_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    latest_date_q = await session.execute(
        select(func.max(PortfolioRanking.date)).where(PortfolioRanking.horizon == horizon)
    )
    latest_date = latest_date_q.scalar_one_or_none()
    if latest_date is None:
        return []

    stmt = (
        select(PortfolioRanking)
        .where(PortfolioRanking.date == latest_date, PortfolioRanking.horizon == horizon)
        .order_by(PortfolioRanking.rank)
    )
    if top_only:
        stmt = stmt.where(PortfolioRanking.in_topk.is_(True))
    rows = (await session.execute(stmt)).scalars().all()

    tickers = [r.ticker for r in rows]
    closes = await fetch_latest_stock_closes(session, tickers)
    factors = await _compute_factor_scores(session, tickers)

    out: list[dict[str, Any]] = []
    for r in rows:
        f = factors.get(r.ticker, {})
        out.append(
            {
                "date": r.date,
                "ticker": r.ticker,
                "name": STOCKS.get(r.ticker),
                "sector": r.sector,
                "score": float(r.score),
                "rank": int(r.rank),
                "in_topk": bool(r.in_topk),
                "horizon": r.horizon,
                "last_close": closes.get(r.ticker),
                "momentum_score": f.get("momentum_score"),
                "quality_score": f.get("quality_score"),
                "value_score": f.get("value_score"),
            }
        )
    return out


class HoldingRow(BaseModel):
    date: date_t
    ticker: str
    name: str | None = None
    sector: str | None = None
    weight: float
    last_price: float | None = None


class EquityPoint(BaseModel):
    date: date_t
    equity: float
    benchmark_equity: float | None = None
    daily_return: float | None = None
    turnover: float | None = None


class PortfolioResponse(BaseModel):
    as_of: date_t | None
    holdings: list[HoldingRow]
    equity_curve: list[EquityPoint]


@router.get("/portfolio", response_model=PortfolioResponse)
async def api_stock_portfolio(
    days: int = Query(365, ge=10, le=2000),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Latest holdings snapshot
    latest_q = await session.execute(select(func.max(PortfolioHolding.date)))
    latest_date = latest_q.scalar_one_or_none()
    holdings_rows: list[dict[str, Any]] = []
    if latest_date is not None:
        h_res = await session.execute(
            select(PortfolioHolding)
            .where(PortfolioHolding.date == latest_date)
            .order_by(desc(PortfolioHolding.weight))
        )
        for h in h_res.scalars().all():
            holdings_rows.append(
                {
                    "date": h.date,
                    "ticker": h.ticker,
                    "name": STOCKS.get(h.ticker),
                    "sector": h.sector,
                    "weight": float(h.weight),
                    "last_price": float(h.last_price) if h.last_price is not None else None,
                }
            )

    # Equity curve over the requested window
    cutoff = (latest_date or datetime.now(tz=UTC).date()) - timedelta(days=days)
    eq_res = await session.execute(
        select(PortfolioEquity)
        .where(PortfolioEquity.date >= cutoff)
        .order_by(PortfolioEquity.date)
    )
    eq_rows: list[dict[str, Any]] = []
    for e in eq_res.scalars().all():
        eq_rows.append(
            {
                "date": e.date,
                "equity": float(e.equity),
                "benchmark_equity": float(e.benchmark_equity)
                if e.benchmark_equity is not None
                else None,
                "daily_return": float(e.daily_return) if e.daily_return is not None else None,
                "turnover": float(e.turnover) if e.turnover is not None else None,
            }
        )

    return {"as_of": latest_date, "holdings": holdings_rows, "equity_curve": eq_rows}


# ----------------------------------------------------------------------------
# Backtest summary + model stats
# ----------------------------------------------------------------------------


@router.get("/backtest")
async def api_stock_backtest(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    res = await session.execute(
        select(BacktestResult)
        .where(BacktestResult.asset_class == "stock", BacktestResult.ticker == "PANEL")
        .order_by(desc(BacktestResult.run_at), desc(BacktestResult.id))
        .limit(1)
    )
    row = res.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No stock portfolio backtest yet.")
    return {
        "horizon": row.horizon,
        "run_at": row.run_at.isoformat() if row.run_at else None,
        "total_return": float(row.total_return or 0.0),
        "sharpe_ratio": float(row.sharpe_ratio or 0.0),
        "max_drawdown": float(row.max_drawdown or 0.0),
        "win_rate": float(row.win_rate or 0.0),
        # Repurposed columns:
        "benchmark_total_return": float(row.avg_win_pct or 0.0),
        "info_ratio_vs_benchmark": float(row.avg_loss_pct or 0.0),
        "num_rebalances": int(row.num_trades or 0),
    }


@router.get("/model-stats")
async def api_stock_model_stats(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    res = await session.execute(
        select(ModelRun)
        .where(ModelRun.asset_class == "stock", ModelRun.ticker == "PANEL")
        .order_by(desc(ModelRun.trained_at), ModelRun.fold)
        .limit(64)
    )
    rows = res.scalars().all()
    return [
        {
            "fold": int(r.fold) if r.fold is not None else None,
            "horizon": r.horizon,
            "trained_at": r.trained_at.isoformat() if r.trained_at else None,
            "ic": float(r.oos_auc or 0.0),
            "rank_ic": float(r.oos_precision or 0.0),
            "top_minus_bottom": float(r.oos_recall or 0.0),
            "mae": float(r.brier_score or 0.0),
        }
        for r in rows
    ]


# ----------------------------------------------------------------------------
# Single-stock detail + history
# ----------------------------------------------------------------------------


@router.get("/{ticker}/history")
async def api_stock_history(
    ticker: str,
    days: int = Query(180, ge=10, le=2000),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    if ticker not in STOCKS and ticker != BENCHMARK_TICKER:
        raise HTTPException(status_code=404, detail="Unknown stock ticker.")
    latest_q = await session.execute(
        select(func.max(StockPrice.date)).where(StockPrice.ticker == ticker)
    )
    latest = latest_q.scalar_one_or_none()
    if latest is None:
        return []
    cutoff = latest - timedelta(days=days)
    res = await session.execute(
        select(StockPrice.date, StockPrice.close)
        .where(StockPrice.ticker == ticker, StockPrice.date >= cutoff)
        .order_by(StockPrice.date)
    )
    return [{"date": d, "close": float(c)} for d, c in res.all() if c is not None]


@router.get("/{ticker}")
async def api_stock_detail(
    ticker: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if ticker not in STOCKS:
        raise HTTPException(status_code=404, detail="Unknown stock ticker.")

    closes = await fetch_latest_stock_closes(session, [ticker])
    rk_q = await session.execute(
        select(PortfolioRanking)
        .where(PortfolioRanking.ticker == ticker)
        .order_by(desc(PortfolioRanking.date))
        .limit(1)
    )
    rk = rk_q.scalars().first()
    meta_q = await session.execute(
        select(InstrumentMetadata)
        .where(InstrumentMetadata.ticker == ticker, InstrumentMetadata.asset_class == "stock")
        .limit(1)
    )
    meta = meta_q.scalars().first()

    return {
        "ticker": ticker,
        "name": STOCKS.get(ticker, ticker),
        "sector": (meta.sector if meta else STOCK_SECTORS.get(ticker)),
        "industry": (meta.industry if meta else STOCK_INDUSTRIES.get(ticker)),
        "last_close": closes.get(ticker),
        "ranking": (
            {
                "date": rk.date.isoformat(),
                "score": float(rk.score),
                "rank": int(rk.rank),
                "in_topk": bool(rk.in_topk),
                "horizon": rk.horizon,
            }
            if rk is not None
            else None
        ),
    }


# ----------------------------------------------------------------------------
# Async refresh / retrain
# ----------------------------------------------------------------------------


class JobResponse(BaseModel):
    job_id: str
    status: str
    name: str


async def _stock_refresh_task(job_id: str) -> None:
    try:
        await mark_running(job_id, "ingesting prices + ranking")
        async with async_session_factory() as session:
            ingest = await refresh_stocks_data(session)
            await run_daily_ranking(session)
        msg = (
            f"rows={ingest.get('rows_persisted')} "
            f"batches={ingest.get('batches')} "
            f"failed={ingest.get('failed_batches')}"
        )
        await complete_job(job_id, msg)
        LOGGER.info("Stock refresh %s completed: %s", job_id, msg)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Stock refresh %s failed.", job_id)
        await fail_job(job_id, str(exc)[:512])


async def _stock_retrain_task(job_id: str) -> None:
    try:
        await mark_running(job_id, "training panel model")
        async with async_session_factory() as session:
            train_summary = await train_stocks_panel(session, target_horizon=5)
            await mark_running(job_id, f"folds={train_summary.get('folds')} backtesting")
            await run_portfolio_backtest(session, target_horizon=5)
            await run_daily_ranking(session, target_horizon=5)
        await complete_job(job_id, f"folds={train_summary.get('folds')} retrain+backtest ok")
        LOGGER.info("Stock retrain+backtest %s completed.", job_id)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Stock retrain %s failed.", job_id)
        await fail_job(job_id, str(exc)[:512])


@router.post("/refresh", response_model=JobResponse, dependencies=[Depends(require_api_key)])
async def api_stock_refresh(background_tasks: BackgroundTasks) -> JobResponse:
    job_id = await start_job("stock_refresh")
    background_tasks.add_task(_stock_refresh_task, job_id)
    return JobResponse(job_id=job_id, status="pending", name="stock_refresh")


@router.post("/retrain", response_model=JobResponse, dependencies=[Depends(require_api_key)])
async def api_stock_retrain(background_tasks: BackgroundTasks) -> JobResponse:
    job_id = await start_job("stock_retrain")
    background_tasks.add_task(_stock_retrain_task, job_id)
    return JobResponse(job_id=job_id, status="pending", name="stock_retrain")
