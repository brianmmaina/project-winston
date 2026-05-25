"""
One-off bootstrap: ingest external data, materialize regimes, train all horizons,
persist OOS/backtests, and warm Redis caches so dashboards work immediately after deploy.
"""

from __future__ import annotations

import asyncio
import logging

from app.constants import REDIS_SIGNAL_FILTERED_KEY, REDIS_SIGNAL_META_KEY, REDIS_SIGNAL_RAW_KEY
from app.core.redis_client import cache_save_json
from app.db.session import async_session_factory
from app.ml.trainer import train_all_tickers
from app.services.signals_service import gather_training_frames, refresh_external_data, run_signal_refresh

LOGGER = logging.getLogger(__name__)


async def bootstrap() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    LOGGER.info("Ingestion + training pipeline…")
    async with async_session_factory() as session:
        await refresh_external_data(session)
        frames = await gather_training_frames(session)
        LOGGER.info("Training %s commodities…", len(frames))
        await train_all_tickers(session, frames)

    LOGGER.info("Computing live signals + warming Redis caches…")
    async with async_session_factory() as session:
        result = await run_signal_refresh(session)
    await cache_save_json(REDIS_SIGNAL_FILTERED_KEY, result["filtered"])
    await cache_save_json(REDIS_SIGNAL_RAW_KEY, result["raw"])
    meta = {
        "refreshed_at": result["refreshed_at"],
        "last_refresh": result["refreshed_at"],
        "filtered_count": result["filtered_count"],
        "ingestion": result["ingestion"],
        "source": "initial_data_load",
    }
    await cache_save_json(REDIS_SIGNAL_META_KEY, meta)
    LOGGER.info("Bootstrap complete (%s filtered signals).", result["filtered_count"])


def main() -> None:
    try:
        asyncio.run(bootstrap())
    except Exception:
        LOGGER.exception("Bootstrap aborted.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
