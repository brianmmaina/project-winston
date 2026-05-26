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

from app.agents.daily_scan import run_daily_scan
from app.constants import COMMODITIES, HORIZONS, REDIS_SIGNAL_FILTERED_KEY, REDIS_SIGNAL_META_KEY, REDIS_SIGNAL_RAW_KEY
from app.data.calendar_fetcher import ingest_earnings_calendar, ingest_economic_calendar
from app.data.cot_fetcher import ingest_cot_data
from app.data.eia_fetcher import ingest_eia_data
from app.data.usda_fetcher import ingest_usda
from app.services.alerts_service import check_price_alerts
from app.services.price_monitor import check_price_thresholds
from app.services.recommendations_service import check_outcomes
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

    async def daily_agent_scan() -> None:
        try:
            await run_daily_scan()
        except Exception:
            LOGGER.exception("Daily agent scan failed")

    async def daily_outcome_check() -> None:
        try:
            async with async_session_factory() as session:
                n = await check_outcomes(session)
            LOGGER.info("Outcome check updated %d records", n)
        except Exception:
            LOGGER.exception("Outcome check failed")

    sched.add_job(
        daily_agent_scan,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        id="daily_agent_scan",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        daily_outcome_check,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=30),
        id="daily_outcome_check",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # ------------------------------------------------------------------
    # Phase 3/4 — COT, EIA, calendar, and price alert jobs
    # ------------------------------------------------------------------

    async def weekly_cot_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                n = await ingest_cot_data(session, years_back=1)
            LOGGER.info("COT ingest: %d rows", n)
        except Exception:
            LOGGER.exception("COT ingest failed")

    async def weekly_eia_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                n = await ingest_eia_data(session, weeks_back=52)
            LOGGER.info("EIA ingest: %d rows", n)
        except Exception:
            LOGGER.exception("EIA ingest failed")

    async def weekly_calendar_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                econ = await ingest_economic_calendar(session)
                from app.services.stocks_service import get_active_tickers
                tickers = await get_active_tickers(session)
                earnings = await ingest_earnings_calendar(session, tickers[:100])  # top 100 to avoid rate limits
            LOGGER.info("Calendar ingest: %d econ events, %d earnings events", econ, earnings)
        except Exception:
            LOGGER.exception("Calendar ingest failed")

    async def price_alert_scan() -> None:
        try:
            async with async_session_factory() as session:
                n = await check_price_alerts(session)
            LOGGER.info("Price alert scan: %d alerts", n)
        except Exception:
            LOGGER.exception("Price alert scan failed")

    async def price_threshold_monitor() -> None:
        try:
            async with async_session_factory() as session:
                triggered = await check_price_thresholds(session)
            if triggered:
                LOGGER.info("Price threshold monitor: %d trigger(s): %s",
                            len(triggered), [t["ticker"] for t in triggered])
        except Exception:
            LOGGER.exception("Price threshold monitor failed")

    async def monthly_usda_pipeline() -> None:
        try:
            async with async_session_factory() as session:
                result = await ingest_usda(session)
            LOGGER.info("USDA ingest: %d rows upserted", result.get("rows_upserted", 0))
        except Exception:
            LOGGER.exception("USDA ingest failed")

    async def daily_paper_mtm() -> None:
        from app.services.paper_trading_service import mark_to_market
        try:
            async with async_session_factory() as session:
                result = await mark_to_market(session)
                await session.commit()
            LOGGER.info("Paper MTM: updated=%d stopped_out=%s", result["updated"], result["stopped_out"])
        except Exception:
            LOGGER.exception("Paper mark-to-market failed")

    async def intraday_paper_mtm() -> None:
        """Refresh prices + check stops for open positions every 2 min during market hours."""
        from app.services.paper_trading_service import mark_to_market
        try:
            async with async_session_factory() as session:
                result = await mark_to_market(session)
                await session.commit()
            if result["updated"] > 0 or result["stopped_out"]:
                LOGGER.debug(
                    "Intraday paper MTM: updated=%d stopped_out=%s",
                    result["updated"], result["stopped_out"],
                )
        except Exception:
            LOGGER.exception("Intraday paper MTM failed")

    sched.add_job(
        daily_paper_mtm,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=30),
        id="paper_mtm",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        intraday_paper_mtm,
        CronTrigger(day_of_week="mon-fri", hour="9-16", minute="*/2"),
        id="intraday_paper_mtm",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    async def daily_agent_analysis() -> None:
        """Full 11-agent pipeline — only runs if AGENT_ANALYSIS_SCHEDULED=true."""
        from app.agents.pipeline import run_agent_pipeline
        try:
            async with async_session_factory() as session:
                result = await run_agent_pipeline(session)
            LOGGER.info(
                "Scheduled agent analysis complete: overseer_ok=%s sub_agents=%d/%d",
                result["overseer"]["error"] is None,
                result["sub_agent_success_count"],
                result["sub_agent_count"],
            )
        except Exception:
            LOGGER.exception("Scheduled agent analysis failed")

    sched.add_job(
        weekly_cot_pipeline,
        CronTrigger(day_of_week="wed", hour=9, minute=0),
        id="weekly_cot",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=7200,
    )

    sched.add_job(
        weekly_eia_pipeline,
        CronTrigger(day_of_week="wed", hour=10, minute=30),
        id="weekly_eia",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        weekly_calendar_pipeline,
        CronTrigger(day_of_week="sun", hour=6, minute=0),
        id="weekly_calendar",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    sched.add_job(
        price_alert_scan,
        CronTrigger(day_of_week="mon-fri", hour="9-16", minute="0,30"),
        id="price_alert_scan",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )

    sched.add_job(
        price_threshold_monitor,
        CronTrigger(day_of_week="mon-fri", hour="9-16", minute="0,15,30,45"),
        id="price_threshold_monitor",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=900,
    )

    sched.add_job(
        monthly_usda_pipeline,
        CronTrigger(day=10, hour=3, minute=0),
        id="monthly_usda",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=7200,
    )

    if settings.agent_analysis_scheduled and settings.anthropic_api_key:
        sched.add_job(
            daily_agent_analysis,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=0),
            id="daily_agent_analysis",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        LOGGER.info("Scheduled daily agent analysis at 09:00 NY (AGENT_ANALYSIS_SCHEDULED=true)")

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
