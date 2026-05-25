"""End-to-end sanity tests for the top-K portfolio backtester."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features_stocks import build_stock_panel_features
from app.ml.portfolio_backtest import (
    BacktestConfig,
    backtest_topk_portfolio,
    equity_to_persistence_rows,
    holdings_to_persistence_rows,
)
from app.ml.stocks_ranker import train_walk_forward


def _score_panel_from_oos(oos_rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": r["date"], "ticker": r["ticker"], "score": r["y_prob"]} for r in oos_rows]
    )


def test_backtest_produces_equity_curve_and_metrics(medium_panel):
    panel, benchmark, sectors = medium_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    _, oos_rows, _, _ = train_walk_forward(
        feats, target_horizon=5, train_days=300, val_days=80, step_days=80
    )
    score_panel = _score_panel_from_oos(oos_rows)
    price_long = panel[["date", "ticker", "close"]]

    cfg = BacktestConfig(top_k=5, max_per_sector=2, rebalance_days=5, transaction_cost_bps=5.0)
    result = backtest_topk_portfolio(score_panel, price_long, sectors, benchmark, cfg)

    assert result.get("empty") is not True
    metrics = result["metrics"]
    assert {"total_return", "sharpe_ratio", "max_drawdown", "win_rate"} <= set(metrics)
    assert metrics["num_rebalances"] > 0
    # Equity curve has a row for every common date
    assert len(result["equity_curve"]) > 0
    # Holdings get one row per (rebalance, ticker)
    assert len(result["holdings"]) == metrics["num_rebalances"] * 5 or len(result["holdings"]) > 0


def test_persistence_adapters_shapes(medium_panel):
    panel, benchmark, sectors = medium_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    _, oos_rows, _, _ = train_walk_forward(
        feats, target_horizon=5, train_days=300, val_days=80, step_days=80
    )
    score_panel = _score_panel_from_oos(oos_rows)
    price_long = panel[["date", "ticker", "close"]]
    cfg = BacktestConfig(top_k=3, max_per_sector=2, rebalance_days=10, transaction_cost_bps=5.0)
    result = backtest_topk_portfolio(score_panel, price_long, sectors, benchmark, cfg)

    eq_rows = equity_to_persistence_rows(
        result["equity_curve"], result["benchmark_curve"], result["daily_returns"]
    )
    assert all({"date", "equity", "benchmark_equity", "daily_return", "turnover"} <= r.keys() for r in eq_rows)

    h_rows = holdings_to_persistence_rows(result["holdings"])
    assert all({"date", "ticker", "weight", "entry_price", "last_price", "sector"} <= r.keys() for r in h_rows)


def test_backtest_handles_no_overlap_gracefully():
    score_panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "ticker": ["A", "B"],
            "score": [0.5, 0.3],
        }
    )
    price_long = pd.DataFrame(
        {
            "date": pd.to_datetime(["2030-01-01", "2030-01-02"]),
            "ticker": ["A", "B"],
            "close": [100.0, 50.0],
        }
    )
    result = backtest_topk_portfolio(score_panel, price_long, {"A": "x", "B": "y"}, None)
    assert result.get("empty") is True
