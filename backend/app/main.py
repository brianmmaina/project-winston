"""FastAPI application entrypoint."""

from __future__ import annotations

import os
import logging

# Must be set before any torch/OpenMP import.
# Apple Silicon has multiple libomp.dylib (Homebrew + PyTorch + sklearn) that
# conflict during parallel barrier synchronisation — this prevents the SIGSEGV.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_analysis import router as agent_analysis_router
from app.api.alerts import router as alerts_router
from app.api.calendar import router as calendar_router
from app.api.data_ingest import router as data_ingest_router
from app.api.deps import get_session
from app.api.jobs import router as jobs_router
from app.api.paper_trading import router as paper_trading_router
from app.api.stocks import router as stocks_router
from app.constants import (
    COMMODITIES,
    REDIS_PORTFOLIO_RISK_KEY,
    REDIS_SIGNAL_FILTERED_KEY,
    REDIS_SIGNAL_META_KEY,
    REDIS_SIGNAL_RAW_KEY,
)
from app.core.config import get_settings, parse_cors
from app.core.redis_client import cache_load_json, cache_save_json
from app.core.security import require_api_key
from app.db.models import BacktestResult, ModelRun
from app.db.operations import fetch_latest_closes, load_close_history
from app.db.session import async_session_factory
from app.ml.trainer import train_all_tickers
from app.scheduler import build_scheduler, shutdown_scheduler

from app.services.jobs_service import (
    complete_job,
    fail_job,
    mark_running,
    start_job,
)
from app.services.signals_service import fetch_latest_backtest, gather_training_frames, run_signal_refresh

LOGGER = logging.getLogger(__name__)


async def _migrate_agent_memory_embedding() -> None:
    """Add embedding_json column to agent_memory if it doesn't exist yet."""
    from sqlalchemy import text as _text
    try:
        async with async_session_factory() as session:
            await session.execute(_text(
                "ALTER TABLE agent_memory ADD COLUMN IF NOT EXISTS embedding_json JSONB"
            ))
            await session.commit()
    except Exception as exc:
        logging.getLogger(__name__).warning("agent_memory embedding migration skipped: %s", exc)


async def _migrate_paper_trading() -> None:
    """Create paper trading tables if they don't exist."""
    from sqlalchemy import text as _text
    statements = [
        """CREATE TABLE IF NOT EXISTS paper_portfolio (
            id SERIAL PRIMARY KEY,
            initial_capital NUMERIC(18,2) NOT NULL DEFAULT 100000,
            current_cash NUMERIC(18,2) NOT NULL,
            spx_entry_price NUMERIC(18,4),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS paper_positions (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(16) NOT NULL,
            name VARCHAR(128),
            sector VARCHAR(64),
            asset_class VARCHAR(16),
            entry_price NUMERIC(18,4) NOT NULL,
            entry_date TIMESTAMPTZ DEFAULT NOW(),
            shares NUMERIC(18,6) NOT NULL,
            position_size_pct NUMERIC(8,4) NOT NULL,
            stop_loss_price NUMERIC(18,4) NOT NULL,
            current_price NUMERIC(18,4),
            recommendation VARCHAR(16) NOT NULL,
            conviction VARCHAR(16),
            thesis TEXT,
            what_breaks_thesis TEXT,
            source_run_id VARCHAR(64),
            is_open BOOLEAN NOT NULL DEFAULT TRUE,
            closed_at TIMESTAMPTZ,
            close_price NUMERIC(18,4),
            close_reason VARCHAR(64),
            realized_pnl_pct NUMERIC(10,4)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_paper_pos_ticker ON paper_positions(ticker)",
        "CREATE INDEX IF NOT EXISTS ix_paper_pos_is_open ON paper_positions(is_open)",
        """CREATE TABLE IF NOT EXISTS paper_trades (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(16) NOT NULL,
            direction VARCHAR(8) NOT NULL,
            price NUMERIC(18,4) NOT NULL,
            shares NUMERIC(18,6) NOT NULL,
            value NUMERIC(18,2) NOT NULL,
            pnl_pct NUMERIC(10,4),
            reason VARCHAR(64) NOT NULL,
            traded_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_paper_trade_ticker ON paper_trades(ticker)",
    ]
    try:
        async with async_session_factory() as session:
            for stmt in statements:
                await session.execute(_text(stmt))
            await session.commit()
    except Exception as exc:
        logging.getLogger(__name__).warning("Paper trading migration skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _migrate_agent_memory_embedding()
    await _migrate_paper_trading()
    scheduler = build_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler(scheduler)


def build_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="Commodity Trading Advisor", lifespan=lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=parse_cors(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(stocks_router)
    application.include_router(jobs_router)
    application.include_router(agent_analysis_router)
    application.include_router(alerts_router)
    application.include_router(calendar_router)
    application.include_router(data_ingest_router)
    application.include_router(paper_trading_router)
    return application


app = build_app()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _fetch_batch_prices_sync(tickers: list[str]) -> dict[str, float | None]:
    """Batch price fetch via yfinance — runs in a thread pool."""
    import pandas as pd
    import yfinance as yf

    result: dict[str, float | None] = {t: None for t in tickers}
    try:
        data = yf.download(tickers, period="1d", progress=False, auto_adjust=True)
        if data.empty:
            return result
        close = data["Close"]
        if isinstance(close, pd.Series):
            clean = close.dropna()
            if not clean.empty:
                result[tickers[0]] = float(clean.iloc[-1])
        else:
            last = close.iloc[-1]
            for t in tickers:
                if t in last.index and pd.notna(last[t]):
                    result[t] = float(last[t])
    except Exception:
        pass
    return result


@app.get("/api/prices/live")
async def api_live_prices(tickers: str) -> dict[str, float | None]:
    """Return latest prices for a comma-separated list of tickers.

    Results are Redis-cached for 90 seconds so multiple clients don't pile up
    yfinance requests. Max 50 tickers per call.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No tickers provided")
    if len(ticker_list) > 50:
        raise HTTPException(status_code=400, detail="Max 50 tickers per request")

    cache_key = f"live_prices:{','.join(sorted(ticker_list))}"
    cached = await cache_load_json(cache_key)
    if cached is not None:
        return cached

    prices = await asyncio.to_thread(_fetch_batch_prices_sync, ticker_list)
    await cache_save_json(cache_key, prices, ttl_seconds=90)
    return prices


class RefreshResponse(BaseModel):
    ingestion: dict[str, Any]
    filtered_count: int
    refreshed_at: str


async def _cache_signal_bundle(result: dict[str, Any]) -> None:
    await cache_save_json(REDIS_SIGNAL_FILTERED_KEY, result["filtered"])
    await cache_save_json(REDIS_SIGNAL_RAW_KEY, result["raw"])
    meta = {
        "refreshed_at": result["refreshed_at"],
        "last_refresh": result["refreshed_at"],
        "filtered_count": result["filtered_count"],
        "ingestion": result["ingestion"],
        "source": "api_refresh",
    }
    await cache_save_json(REDIS_SIGNAL_META_KEY, meta)
    if "risk" in result:
        await cache_save_json(REDIS_PORTFOLIO_RISK_KEY, result["risk"])


@app.post("/api/refresh", response_model=RefreshResponse, dependencies=[Depends(require_api_key)])
async def api_refresh(session: AsyncSession = Depends(get_session)):
    """Synchronous full refresh. Kept for ergonomics / parity with v1.

    For UIs, prefer ``POST /api/refresh-async`` which returns a job_id and lets
    the client poll ``GET /api/jobs/{job_id}`` rather than holding a long HTTP
    request open.
    """
    result = await run_signal_refresh(session)
    await _cache_signal_bundle(result)
    return RefreshResponse(
        ingestion=result["ingestion"],
        filtered_count=result["filtered_count"],
        refreshed_at=result["refreshed_at"],
    )


class JobStartResponse(BaseModel):
    job_id: str
    status: str
    name: str


async def _async_refresh_task(job_id: str) -> None:
    try:
        await mark_running(job_id, "running signal refresh")
        async with async_session_factory() as session:
            result = await run_signal_refresh(session)
            await _cache_signal_bundle(result)
        await complete_job(
            job_id,
            f"filtered={result['filtered_count']} refreshed_at={result['refreshed_at']}",
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Commodity refresh %s failed", job_id)
        await fail_job(job_id, str(exc)[:512])


@app.post(
    "/api/refresh-async",
    response_model=JobStartResponse,
    dependencies=[Depends(require_api_key)],
)
async def api_refresh_async(background_tasks: BackgroundTasks) -> JobStartResponse:
    job_id = await start_job("commodity_refresh")
    background_tasks.add_task(_async_refresh_task, job_id)
    return JobStartResponse(job_id=job_id, status="pending", name="commodity_refresh")


@app.get("/api/meta")
async def api_meta() -> dict[str, Any]:
    meta = await cache_load_json(REDIS_SIGNAL_META_KEY)
    if meta is None:
        raise HTTPException(status_code=404, detail="No refresh metadata in cache; call POST /api/refresh first.")
    if "last_refresh" not in meta and "refreshed_at" in meta:
        meta = {**meta, "last_refresh": meta["refreshed_at"]}
    return meta


@app.get("/api/signals")
async def api_signals() -> list[dict[str, Any]]:
    data = await cache_load_json(REDIS_SIGNAL_FILTERED_KEY)
    if data is None:
        raise HTTPException(status_code=503, detail="Signals cache empty; call POST /api/refresh first.")
    return data


@app.get("/api/signals/raw")
async def api_signals_raw() -> list[dict[str, Any]]:
    data = await cache_load_json(REDIS_SIGNAL_RAW_KEY)
    if data is None:
        raise HTTPException(status_code=503, detail="Raw signals cache empty; call POST /api/refresh first.")
    return data


@app.get("/api/portfolio/risk")
async def api_portfolio_risk() -> dict[str, Any]:
    data = await cache_load_json(REDIS_PORTFOLIO_RISK_KEY)
    if data is None:
        raise HTTPException(status_code=503, detail="Portfolio risk cache empty; call POST /api/refresh first.")
    return data


@app.get("/api/events/price-triggers")
async def api_price_triggers() -> dict[str, Any]:
    """Return recent intraday price threshold events (>3% deviation from 20d SMA)."""
    from app.services.price_monitor import get_recent_price_triggers
    events = await get_recent_price_triggers()
    return {"events": events, "count": len(events)}


@app.get("/api/signals/{ticker:path}")
async def api_signal_detail(ticker: str) -> dict[str, Any]:
    if ticker not in COMMODITIES:
        raise HTTPException(status_code=404, detail="Unknown commodity ticker.")
    cached = await cache_load_json(REDIS_SIGNAL_FILTERED_KEY)
    if cached is None:
        raise HTTPException(status_code=503, detail="Signals cache empty; call POST /api/refresh first.")
    for row in cached:
        if str(row.get("ticker")) == ticker:
            return row
    raise HTTPException(status_code=404, detail="Ticker not present in last refresh batch.")


@app.get("/api/commodities")
async def api_commodities(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    tickers = list(COMMODITIES.keys())
    closes = await fetch_latest_closes(session, tickers)
    return [{"ticker": t, "name": COMMODITIES[t], "last_close": closes.get(t)} for t in tickers]


def _serialize_backtest_summary_row(rv: BacktestResult) -> dict[str, Any]:
    def xf(v: Decimal | None) -> float:
        return float(v) if v is not None else 0.0

    nt = rv.num_trades if rv.num_trades is not None else 0
    return {
        "ticker": rv.ticker,
        "horizon": rv.horizon,
        "name": COMMODITIES.get(rv.ticker, rv.ticker),
        "total_return": xf(rv.total_return),
        "sharpe_ratio": xf(rv.sharpe_ratio),
        "max_drawdown": xf(rv.max_drawdown),
        "win_rate": xf(rv.win_rate),
        "num_trades": int(nt),
        "run_at": rv.run_at.isoformat() if rv.run_at else None,
    }


@app.get("/api/backtest")
async def api_backtest_board(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    res = await session.execute(select(BacktestResult).where(BacktestResult.ticker.in_(list(COMMODITIES.keys()))))
    rows_all = list(res.scalars().all())
    by_te: defaultdict[str, list[BacktestResult]] = defaultdict(list)
    for rv in rows_all:
        by_te[rv.ticker].append(rv)

    sentinel = datetime(1970, 1, 1, tzinfo=UTC)

    def rk(r: BacktestResult) -> datetime:
        return r.run_at or sentinel

    out: list[dict[str, Any]] = []
    for ticker in COMMODITIES:
        bucket = by_te.get(ticker, [])
        if not bucket:
            continue
        h21 = [r for r in bucket if r.horizon == "21d"]
        choice = max(h21, key=rk) if h21 else max(bucket, key=rk)
        out.append(_serialize_backtest_summary_row(choice))
    return out


@app.get("/api/commodities/{ticker:path}/cot")
async def api_commodity_cot(
    ticker: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if ticker not in COMMODITIES:
        raise HTTPException(status_code=404, detail="Unknown commodity ticker.")
    from app.data.cot_fetcher import get_latest_cot, get_cot_history
    latest = await get_latest_cot(session, ticker)
    history = await get_cot_history(session, ticker, weeks=52)
    return {"latest": latest, "history": history}


@app.get("/api/commodities/{ticker:path}/history")
async def api_commodity_history(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    days: int = 180,
) -> list[dict[str, Any]]:
    if ticker not in COMMODITIES:
        raise HTTPException(status_code=404, detail="Unknown commodity ticker.")
    hist = await load_close_history(session, [ticker], lookback_days=days)
    bars = sorted(hist.get(ticker, []), key=lambda pair: pair[0])
    return [
        {
            "date": dt.isoformat() if hasattr(dt, "isoformat") else str(dt),
            "close": float(clo),
        }
        for dt, clo in bars
    ]


@app.get("/api/backtest/{ticker:path}")
async def api_backtest(ticker: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if ticker not in COMMODITIES:
        raise HTTPException(status_code=404, detail="Unknown commodity ticker.")
    return await fetch_latest_backtest(session, ticker)


def _float_or_none(v: Decimal | None) -> float | None:
    if v is None:
        return None
    return float(v)


def _serialize_model_run(row: ModelRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "ticker": row.ticker,
        "horizon": row.horizon,
        "trained_at": row.trained_at.isoformat() if row.trained_at else None,
        "oos_auc": _float_or_none(row.oos_auc),
        "oos_precision": _float_or_none(row.oos_precision),
        "oos_recall": _float_or_none(row.oos_recall),
        "brier_score": _float_or_none(row.brier_score),
        "fold": row.fold,
    }


@app.get("/api/model-stats/{ticker:path}")
async def api_model_stats(ticker: str, session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    if ticker not in COMMODITIES:
        raise HTTPException(status_code=404, detail="Unknown commodity ticker.")
    q = await session.execute(
        select(ModelRun)
        .where(ModelRun.ticker == ticker)
        .order_by(desc(ModelRun.trained_at), desc(ModelRun.id))
        .limit(64)
    )
    rows = q.scalars().all()
    return [_serialize_model_run(r) for r in rows]


class RetrainResponse(BaseModel):
    job_id: str
    status: str
    name: str


async def _retrain_task(job_id: str) -> None:
    try:
        await mark_running(job_id, "gathering training frames")
        async with async_session_factory() as session:
            frames = await gather_training_frames(session)
            await mark_running(job_id, f"training {len(frames)} tickers")
            await train_all_tickers(session, frames)
        await complete_job(job_id, f"trained {len(frames)} tickers")
        LOGGER.info("Retrain job %s completed.", job_id)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Retrain job %s failed.", job_id)
        await fail_job(job_id, str(exc)[:512])


@app.post("/api/retrain", response_model=RetrainResponse, dependencies=[Depends(require_api_key)])
async def api_retrain(background_tasks: BackgroundTasks) -> RetrainResponse:
    job_id = await start_job("commodity_retrain")
    background_tasks.add_task(_retrain_task, job_id)
    return RetrainResponse(job_id=job_id, status="pending", name="commodity_retrain")
