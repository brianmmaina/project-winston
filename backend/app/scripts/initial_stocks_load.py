"""One-off bootstrap for the stock universe: seed metadata, batched yfinance pull,
write to ``stock_prices``. Run after applying alembic migration ``002_stocks``.

    docker compose exec backend python -m app.scripts.initial_stocks_load

Idempotent: re-running upserts existing rows. The full S&P 500 (~503 names)
plus the SPY benchmark over a 5-year window typically takes 6-10 minutes
depending on yfinance's rate limiting and your network.
"""

from __future__ import annotations

import asyncio
import logging

from app.data.stocks_fetcher import ingest_stock_prices, seed_instrument_metadata
from app.db.session import async_session_factory

LOGGER = logging.getLogger(__name__)


async def bootstrap() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    LOGGER.info("Seeding instrument_metadata for stocks…")
    async with async_session_factory() as session:
        meta_count = await seed_instrument_metadata(session)
    LOGGER.info("Seeded %d instrument_metadata rows.", meta_count)

    LOGGER.info("Pulling OHLCV for stock universe (this may take several minutes)…")
    async with async_session_factory() as session:
        stats = await ingest_stock_prices(session)
    LOGGER.info(
        "Ingest done: requested=%d rows=%d batches=%d failed_batches=%d",
        stats["requested"],
        stats["rows_persisted"],
        stats["batches"],
        stats["failed_batches"],
    )


def main() -> None:
    try:
        asyncio.run(bootstrap())
    except Exception:
        LOGGER.exception("Stock bootstrap aborted.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
