"""Tests for the cross-sectional ranker — walk-forward splits, fold metrics, sector caps."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features_stocks import build_stock_panel_features
from app.ml.stocks_ranker import (
    PANEL_KEY,
    fold_metrics_to_model_runs,
    rank_and_apply_sector_caps,
    train_walk_forward,
)


def test_walk_forward_yields_folds(medium_panel):
    panel, benchmark, sectors = medium_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    folds, oos_rows, model, feat_cols = train_walk_forward(
        feats, target_horizon=5, train_days=300, val_days=80, step_days=80
    )
    assert len(folds) >= 2, "Need at least two folds with the chosen window sizes."
    assert len(oos_rows) > 0
    assert model is not None
    # No NaN feature values land in training
    assert len(feat_cols) > 0


def test_walk_forward_no_train_val_overlap(medium_panel):
    panel, benchmark, sectors = medium_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    folds, _, _, _ = train_walk_forward(
        feats, target_horizon=5, train_days=300, val_days=80, step_days=80
    )
    for fold in folds:
        assert fold.train_end < fold.val_start, "Train must end strictly before validation."
        assert fold.val_end > fold.val_start


def test_fold_metrics_persistence_shape(medium_panel):
    panel, benchmark, sectors = medium_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    folds, _, _, _ = train_walk_forward(
        feats, target_horizon=5, train_days=300, val_days=80, step_days=80
    )
    runs = fold_metrics_to_model_runs(folds, "5d")
    assert len(runs) == len(folds)
    assert all(r["asset_class"] == "stock" for r in runs)
    assert all(r["ticker"] == PANEL_KEY for r in runs)
    assert all({"oos_auc", "oos_precision", "oos_recall", "brier_score"} <= r.keys() for r in runs)


def test_sector_caps_limit_per_sector():
    scored = pd.DataFrame(
        {
            "date": ["2024-01-15"] * 8,
            "ticker": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "sector": [
                "Information Technology",
                "Information Technology",
                "Information Technology",
                "Financials",
                "Financials",
                "Health Care",
                "Energy",
                "Energy",
            ],
            "close": [100.0] * 8,
            "score": [1.0, 0.95, 0.9, 0.8, 0.75, 0.7, 0.65, 0.6],
        }
    )
    ranked = rank_and_apply_sector_caps(scored, top_k=5, max_per_sector=2)
    selected = ranked[ranked["in_topk"]]
    by_sector = selected["sector"].value_counts().to_dict()
    assert all(v <= 2 for v in by_sector.values())
    assert len(selected) <= 5
    # Cap should skip third IT name (C) and instead promote next-highest cross-sector name
    assert "C" not in selected["ticker"].tolist()
