"""Common pytest fixtures: synthetic panel + benchmark + sector map."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


SECTORS = [
    "Information Technology",
    "Financials",
    "Health Care",
    "Industrials",
    "Energy",
    "Consumer Discretionary",
    "Consumer Staples",
    "Communication Services",
]


def _build_panel(n_tickers: int, n_days: int, *, seed: int = 0) -> tuple[pd.DataFrame, pd.Series, dict[str, str]]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=n_days)
    tickers = [f"STK{i:02d}" for i in range(n_tickers)]
    sectors = {t: SECTORS[i % len(SECTORS)] for i, t in enumerate(tickers)}

    rows: list[dict] = []
    day_factor = rng.normal(0, 0.005, len(dates))
    loadings = rng.normal(1.0, 0.3, len(tickers))
    for j, t in enumerate(tickers):
        diffuse = rng.normal(0.0003, 0.018, len(dates)) + loadings[j] * day_factor
        p = 50.0 * np.exp(np.cumsum(diffuse))
        for d, px in zip(dates, p):
            rows.append(
                {
                    "date": d,
                    "ticker": t,
                    "open": px * 0.999,
                    "high": px * 1.006,
                    "low": px * 0.994,
                    "close": float(px),
                    "volume": 1_000_000,
                    "adj_close": float(px),
                }
            )
    panel = pd.DataFrame(rows)
    bench_p = 50.0 * np.exp(np.cumsum(day_factor + rng.normal(0.0003, 0.010, len(dates))))
    benchmark = pd.Series(bench_p, index=dates, name="SPY")
    return panel, benchmark, sectors


@pytest.fixture
def small_panel() -> tuple[pd.DataFrame, pd.Series, dict[str, str]]:
    return _build_panel(n_tickers=6, n_days=380, seed=1)


@pytest.fixture
def medium_panel() -> tuple[pd.DataFrame, pd.Series, dict[str, str]]:
    return _build_panel(n_tickers=20, n_days=900, seed=3)
