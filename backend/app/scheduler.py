"""Scheduled ingest + inference + Redis cache (APScheduler, NY timezone).

AsyncIOScheduler executes coroutine jobs on the FastAPI event loop.
CPU-heavy work (sklearn fitting, Optuna, vectorbt) must stay inside ``asyncio.to_thread``
in downstream modules so these jobs do not block the loop.
"""

from __future__ import annotations

import logging

import pandas as pd
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import desc, select

from app.constants import COMMODITIES, HORIZONS, REDIS_SIGNAL_FILTERED_KEY, REDIS_SIGNAL_META_KEY, REDIS_SIGNAL_RAW_KEY
from app.core.config import get_settings
from app.core.redis_client import cache_save_json
from app.db.models import ModelRun
from app.db.session import async_session_factory
from app.ml.backtest_jobs import rebuild_backtests_after_training
from app.ml.trainer import train_all_tickers
from app.ml.tuner import optimize_and_store_horizon
from app.services.signals_service import gather_training_frames, materialize_training_frame, run_signal_refresh
from app.services.stocks_service import (
    refresh_stocks_data,
    run_daily_ranking,
    run_portfolio_backtest,
    train_stocks_panel,
)

LOGGER = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler | None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        return None
    tz = pytz.timezone(settings.timezone)
    sched = AsyncIOScheduler(timezone=tz)

    async def daily_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                result = await run_signal_refresh(session)
            await cache_save_json(REDIS_SIGNAL_FILTERED_KEY, result["filtered"])
            await cache_save_json(REDIS_SIGNAL_RAW_KEY, result["raw"])
            meta = {
                "refreshed_at": result["refreshed_at"],
                "last_refresh": result["refreshed_at"],
                "filtered_count": result["filtered_count"],
                "ingestion": result["ingestion"],
                "source": "scheduler",
            }
            await cache_save_json(REDIS_SIGNAL_META_KEY, meta)
        except Exception:
            LOGGER.exception("Scheduled refresh pipeline failed")

    async def weekly_retrain_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                frames = await gather_training_frames(session)
                await train_all_tickers(session, frames)
            LOGGER.info("Weekly retrain job finished.")
        except Exception:
            LOGGER.exception("Weekly retrain pipeline failed.")

    async def weekly_backtest_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                await rebuild_backtests_after_training(session, None)
            LOGGER.info("Weekly backtest job finished.")
        except Exception:
            LOGGER.exception("Weekly backtest pipeline failed.")

    async def monthly_tuning_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                tuned = 0
                frames_cache: dict[str, pd.DataFrame | None] = {}

                async def latest_auc(tt: str, hz: str) -> float | None:
                    qr = await session.execute(
                        select(ModelRun.oos_auc)
                        .where(ModelRun.ticker == tt, ModelRun.horizon == hz)
                        .order_by(desc(ModelRun.trained_at), desc(ModelRun.id))
                        .limit(1)
                    )
                    v = qr.scalar_one_or_none()
                    if v is None:
                        return None
                    return float(v)

                for ticker in COMMODITIES:
                    for horizon in HORIZONS:
                        auc_val = await latest_auc(ticker, horizon)
                        if auc_val is not None and auc_val >= 0.58:
                            continue
                        if ticker not in frames_cache:
                            fr = await materialize_training_frame(session, ticker)
                            frames_cache[ticker] = fr
                        frame_ob = frames_cache[ticker]
                        if frame_ob is None:
                            LOGGER.warning(
                                "Monthly tune skipped: no frame %s horizon %s",
                                ticker,
                                horizon,
                            )
                            continue
                        if await optimize_and_store_horizon(
                            session, ticker, horizon, frame_ob, n_trials=10
                        ):
                            tuned += 1
                await session.commit()
                LOGGER.info("Monthly tuning persisted %s optimization slots.", tuned)
        except Exception:
            LOGGER.exception("Monthly tuning pipeline failed.")

    sched.add_job(
        daily_pipeline,
        CronTrigger(day_of_week="mon-fri", hour=6, minute=30),
        id="commodity_refresh_weekday",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    sched.add_job(
        weekly_retrain_pipeline,
        CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_retrain",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        weekly_backtest_pipeline,
        CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="weekly_backtest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        monthly_tuning_pipeline,
        CronTrigger(day=1, hour=1, minute=0),
        id="monthly_tuning",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # ------------------------------------------------------------------
    # Stock universe pipelines (additive — runs alongside commodity jobs).
    # Daily stock ingest fires after the commodity refresh to avoid yfinance
    # rate-limit pile-ups; weekly retrain runs on Saturday to keep Sunday's
    # weekly_backtest free for commodities, then a stock portfolio backtest
    # follows on Sunday morning.
    # ------------------------------------------------------------------

    async def daily_stock_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                await refresh_stocks_data(session)
                await run_daily_ranking(session, target_horizon=5)
            LOGGER.info("Daily stock pipeline finished.")
        except Exception:
            LOGGER.exception("Daily stock pipeline failed.")

    async def weekly_stock_retrain_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                await train_stocks_panel(session, target_horizon=5)
                await run_portfolio_backtest(session, target_horizon=5)
                await run_daily_ranking(session, target_horizon=5)
            LOGGER.info("Weekly stock retrain + backtest finished.")
        except Exception:
            LOGGER.exception("Weekly stock retrain pipeline failed.")

    sched.add_job(
        daily_stock_pipeline,
        CronTrigger(day_of_week="mon-fri", hour=7, minute=15),
        id="stock_refresh_weekday",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        weekly_stock_retrain_pipeline,
        CronTrigger(day_of_week="sat", hour=3, minute=0),
        id="weekly_stock_retrain",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.start()
    LOGGER.info(
        "APScheduler started (commodities: weekday refresh + weekly retrain/backtest + monthly tune | "
        "stocks: weekday refresh + weekly retrain, tz=%s)",
        settings.timezone,
    )
    return sched


def shutdown_scheduler(sched: AsyncIOScheduler | None) -> None:
    if sched is None:
        return
    sched.shutdown(wait=False)
    LOGGER.info("APScheduler shut down")
