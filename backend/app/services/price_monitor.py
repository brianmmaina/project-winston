"""Intraday price threshold monitor.

Checks commodity prices vs their 20-day SMA every 15 minutes during market
hours.  When a price deviates > TRIGGER_PCT from its SMA the event is written
to Redis with a debounce TTL so the same ticker only fires once per window.

Redis layout:
    event:price_trigger:{ticker}  — debounce key, TTL = DEBOUNCE_SECONDS
    event:price_triggers          — JSON list of recent trigger events (capped, TTL = 24 h)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COMMODITIES
from app.core.redis_client import cache_load_json, cache_save_json
from app.db.operations import load_close_history

logger = logging.getLogger(__name__)

TRIGGER_PCT = 3.0          # % deviation from 20d SMA to fire
DEBOUNCE_SECONDS = 4 * 3600  # 4 h — minimum gap between events for the same ticker
SMA_WINDOW = 20
_DEBOUNCE_PREFIX = "event:price_trigger:"
_EVENTS_KEY = "event:price_triggers"
_MAX_EVENTS = 50           # keep the latest N events in Redis


async def check_price_thresholds(session: AsyncSession) -> list[dict[str, Any]]:
    """Return list of tickers whose price just crossed the SMA threshold.

    Already-debounced tickers are skipped.  New triggers are stored in Redis.
    """
    lookback = SMA_WINDOW + 5
    history = await load_close_history(session, list(COMMODITIES.keys()), lookback_days=lookback)

    triggered: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)

    for ticker, pairs in history.items():
        if len(pairs) < SMA_WINDOW:
            continue

        closes = [px for _, px in pairs]
        latest = closes[-1]
        sma = sum(closes[-SMA_WINDOW:]) / SMA_WINDOW
        if sma == 0:
            continue

        deviation_pct = (latest - sma) / sma * 100.0

        if abs(deviation_pct) < TRIGGER_PCT:
            continue

        # Check debounce key
        debounce_key = f"{_DEBOUNCE_PREFIX}{ticker}"
        existing = await cache_load_json(debounce_key)
        if existing is not None:
            continue

        direction = "above" if deviation_pct > 0 else "below"
        event: dict[str, Any] = {
            "ticker": ticker,
            "name": COMMODITIES.get(ticker, ticker),
            "direction": direction,
            "deviation_pct": round(deviation_pct, 2),
            "latest_price": round(latest, 4),
            "sma_20d": round(sma, 4),
            "triggered_at": now.isoformat(),
        }
        triggered.append(event)

        # Write debounce key with TTL
        await cache_save_json(debounce_key, {"triggered_at": now.isoformat()}, ttl_seconds=DEBOUNCE_SECONDS)
        logger.info(
            "Price trigger: %s %s SMA by %.1f%% (price=%.4f sma=%.4f)",
            ticker, direction, abs(deviation_pct), latest, sma,
        )

    if triggered:
        existing_events: list[dict[str, Any]] = (await cache_load_json(_EVENTS_KEY)) or []
        combined = (triggered + existing_events)[:_MAX_EVENTS]
        await cache_save_json(_EVENTS_KEY, combined, ttl_seconds=86400)

    return triggered


async def get_recent_price_triggers() -> list[dict[str, Any]]:
    """Return the most recent price trigger events from Redis."""
    return (await cache_load_json(_EVENTS_KEY)) or []
