"""Smoke tests for the cross-sectional feature builder."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features_stocks import (
    SECTOR_RELATIVE_FEATURES,
    build_stock_panel_features,
    split_features_targets,
    stock_feature_columns,
)


def test_panel_features_shape_and_targets(small_panel):
    panel, benchmark, sectors = small_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    assert not feats.empty
    # All tickers from the panel survive
    assert set(feats["ticker"].unique()) == set(panel["ticker"].unique())
    # Forward targets present
    assert "target_fwd_return_5d" in feats.columns
    assert "target_fwd_return_21d" in feats.columns


def test_forward_targets_nans_concentrated_at_tail(small_panel):
    panel, benchmark, sectors = small_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    for ticker, sub in feats.groupby("ticker"):
        sub_sorted = sub.sort_values("date").reset_index(drop=True)
        nan_idx = sub_sorted.index[sub_sorted["target_fwd_return_5d"].isna()].tolist()
        if not nan_idx:
            continue
        expected_tail = list(range(len(sub_sorted) - 5, len(sub_sorted)))
        assert nan_idx == expected_tail, f"5d NaNs not tail-aligned for {ticker}"


def test_sector_relative_zscores_present(small_panel):
    panel, benchmark, sectors = small_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    expected = {f"{c}_sector_z" for c in SECTOR_RELATIVE_FEATURES if c in feats.columns}
    assert expected.issubset(set(feats.columns))


def test_spy_features_finite(small_panel):
    panel, benchmark, sectors = small_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    for col in ("spy_corr_20d", "spy_rel_return_1d", "spy_rel_return_5d", "spy_rel_return_21d", "spy_regime_bull"):
        assert col in feats.columns
    # Once warm-up windows have passed, values are finite (no inf)
    warm = feats[feats["date"] > pd.Timestamp("2021-06-01")]
    assert np.isfinite(warm[["spy_rel_return_5d", "spy_regime_bull"]].fillna(0.0)).all().all()


def test_split_features_targets_drops_tail_nans(small_panel):
    panel, benchmark, sectors = small_panel
    feats = build_stock_panel_features(panel, benchmark, sectors)
    X, y, meta = split_features_targets(feats, target_horizon=5)
    # Tail of each ticker (5 rows) should be dropped → totals smaller than panel
    expected_total = len(feats) - 5 * len(panel["ticker"].unique())
    assert len(X) == expected_total == len(y) == len(meta)
    # No leakage: every kept row has a finite target
    assert y.notna().all()
    # feature col count matches helper
    assert list(X.columns) == stock_feature_columns(feats)
