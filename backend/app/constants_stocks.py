"""Stock universe loader. Reads the curated JSON snapshot at module import and
exposes a flat ``STOCKS`` mapping plus per-sector membership.

The JSON file at ``backend/app/data/sp500_universe.json`` is the source of truth.
Run ``python -m scripts.refresh_sp500_universe`` to pull the full current S&P 500
constituents from Wikipedia and overwrite the snapshot.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "sp500_universe.json"

# Cross-asset benchmark used by the stock feature engineering (SPY ≈ S&P 500).
BENCHMARK_TICKER: str = "SPY"
BENCHMARK_NAME: str = "SPDR S&P 500 ETF Trust"


def _load_snapshot() -> dict[str, Any]:
    if not _SNAPSHOT_PATH.exists():
        LOGGER.warning(
            "S&P 500 snapshot missing at %s. Stock universe will be empty until "
            "scripts.refresh_sp500_universe is run.",
            _SNAPSHOT_PATH,
        )
        return {"version": "missing", "instruments": []}
    try:
        with _SNAPSHOT_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Failed to read stock universe snapshot: %s", exc)
        return {"version": "error", "instruments": []}


@lru_cache(maxsize=1)
def _universe_payload() -> dict[str, Any]:
    return _load_snapshot()


def stock_universe() -> dict[str, str]:
    """Ticker -> display name."""
    data = _universe_payload()
    return {row["ticker"]: row["name"] for row in data.get("instruments", [])}


def stock_sectors() -> dict[str, str]:
    """Ticker -> GICS sector."""
    data = _universe_payload()
    return {row["ticker"]: row.get("sector") or "Unknown" for row in data.get("instruments", [])}


def stock_industries() -> dict[str, str]:
    data = _universe_payload()
    return {row["ticker"]: row.get("industry") or "Unknown" for row in data.get("instruments", [])}


def sector_membership() -> dict[str, list[str]]:
    """Sector -> [tickers]."""
    by_sector: dict[str, list[str]] = defaultdict(list)
    for ticker, sector in stock_sectors().items():
        by_sector[sector].append(ticker)
    return dict(by_sector)


def universe_metadata() -> dict[str, Any]:
    data = _universe_payload()
    return {
        "version": data.get("version"),
        "source": data.get("source"),
        "size": len(data.get("instruments", [])),
        "benchmark": data.get("benchmark", {"ticker": BENCHMARK_TICKER, "name": BENCHMARK_NAME}),
    }


def reload_universe() -> dict[str, Any]:
    """Drop cache and re-read snapshot (call after running the refresh script)."""
    _universe_payload.cache_clear()
    return universe_metadata()


# Eager-evaluated constants for parity with ``app.constants.COMMODITIES``.
STOCKS: dict[str, str] = stock_universe()
STOCK_SECTORS: dict[str, str] = stock_sectors()
STOCK_INDUSTRIES: dict[str, str] = stock_industries()
SECTOR_MEMBERSHIP: dict[str, list[str]] = sector_membership()
