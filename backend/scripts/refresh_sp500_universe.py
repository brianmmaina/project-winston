"""Refresh the committed S&P 500 universe snapshot from Wikipedia.

Usage (inside backend container or local venv with pandas + lxml installed):

    python -m scripts.refresh_sp500_universe

Writes ``backend/app/data/sp500_universe.json``. The CI/CD pipeline can run this
on a schedule (e.g. monthly) so the universe stays current as constituents change.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "sp500_universe.json"

# Wikipedia rejects the default urllib UA; spoof a real browser identifier.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "commodity-advisor/0.2 (+https://github.com/brianmmaina/commodity-advisor)"
)

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _normalise_ticker(raw: str) -> str:
    """Wikipedia uses ``BRK.B``; yfinance uses ``BRK-B``."""
    return raw.strip().replace(".", "-")


def _http_get(url: str, timeout_s: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — fixed URL
        return resp.read().decode("utf-8", errors="replace")


def fetch_constituents() -> list[dict[str, Any]]:
    LOGGER.info("Fetching constituents from %s", WIKI_URL)
    html = _http_get(WIKI_URL)
    tables = pd.read_html(io.StringIO(html))
    if not tables:
        raise RuntimeError("Wikipedia returned zero tables; layout may have changed.")
    main = tables[0]
    expected_cols = {"Symbol", "Security", "GICS Sector"}
    if not expected_cols.issubset(main.columns):
        raise RuntimeError(f"Unexpected columns: {list(main.columns)}")

    industry_col = "GICS Sub-Industry" if "GICS Sub-Industry" in main.columns else None
    rows: list[dict[str, Any]] = []
    for _, r in main.iterrows():
        ticker = _normalise_ticker(str(r["Symbol"]))
        if not ticker:
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": str(r["Security"]).strip(),
                "sector": str(r["GICS Sector"]).strip(),
                "industry": str(r[industry_col]).strip() if industry_col else None,
            }
        )
    rows.sort(key=lambda x: x["ticker"])
    LOGGER.info("Parsed %d constituents.", len(rows))
    return rows


def write_snapshot(instruments: list[dict[str, Any]]) -> None:
    payload = {
        "version": date.today().isoformat(),
        "source": "wikipedia_sp500",
        "benchmark": {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust"},
        "instruments": instruments,
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote snapshot to %s (%d rows).", SNAPSHOT_PATH, len(instruments))


def main() -> int:
    try:
        instruments = fetch_constituents()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Snapshot refresh failed: %s", exc)
        return 1
    if not instruments:
        LOGGER.error("Refusing to overwrite snapshot with zero rows.")
        return 1
    write_snapshot(instruments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
