"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
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
from app.api.deps import get_session
from app.api.jobs import router as jobs_router
from app.api.stocks import router as stocks_router
from app.constants import (
    COMMODITIES,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    return application


app = build_app()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
