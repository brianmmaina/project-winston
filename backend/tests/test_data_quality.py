"""Leakage / drift / target-alignment guards for the stock walk-forward pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.data_quality import (
    check_distribution_drift,
    check_no_infinite_features,
    check_target_alignment,
    check_temporal_separation,
    run_all_checks,
)


def _frame(dates: pd.DatetimeIndex, **extra) -> pd.DataFrame:
    return pd.DataFrame({"date": dates, **extra})


def test_temporal_separation_clean():
    train = _frame(pd.date_range("2020-01-01", "2020-06-30"), x=1.0)
    val = _frame(pd.date_range("2020-07-01", "2020-09-30"), x=2.0)
    out = check_temporal_separation(train, val)
    assert out["passed"] is True
    assert out["issues"] == []


def test_temporal_separation_detects_overlap():
    train = _frame(pd.date_range("2020-01-01", "2020-09-30"), x=1.0)
    val = _frame(pd.date_range("2020-07-01", "2020-12-31"), x=2.0)
    out = check_temporal_separation(train, val)
    assert out["passed"] is False
    assert any("Temporal overlap" in m for m in out["issues"])


def test_temporal_separation_warns_unsorted():
    dates = pd.to_datetime(["2020-01-02", "2020-01-01", "2020-01-03"])
    train = pd.DataFrame({"date": dates, "x": [1.0, 2.0, 3.0]})
    val = pd.DataFrame({"date": pd.date_range("2020-02-01", periods=3), "x": [4, 5, 6]})
    out = check_temporal_separation(train, val)
    # Overlap not present, but warning fires for sort order
    assert any("not sorted" in w for w in out["warnings"])


def test_check_no_infinite_features_detects_inf():
    df = pd.DataFrame({"f1": [1.0, np.inf, 2.0], "f2": [0.0, 0.0, 0.0]})
    out = check_no_infinite_features(df, ["f1", "f2"], label="train")
    assert out["passed"] is False
    assert out["infinite_features"] == ["f1"]


def test_target_alignment_warns_when_no_nans():
    df = pd.DataFrame({"target": [0.01, -0.02, 0.005]})
    out = check_target_alignment(df, target_column="target", forward_days=5)
    assert any("Expected" in w for w in out["warnings"])


def test_distribution_drift_flags_large_shift():
    rng = np.random.default_rng(0)
    train = pd.DataFrame({"f": rng.normal(0, 1, 1000)})
    val = pd.DataFrame({"f": rng.normal(5, 1, 1000)})  # 5σ shift
    out = check_distribution_drift(train, val, ["f"], sigma_threshold=3.0)
    assert any("drift" in w for w in out["warnings"])
    assert out["stats"]["f"]["drift_sigmas"] > 3


def test_run_all_checks_aggregates(small_panel):
    panel, _, _ = small_panel
    train = panel[panel["date"] < "2021-06-01"]
    val = panel[(panel["date"] >= "2021-06-01") & (panel["date"] < "2021-09-01")]
    res = run_all_checks(
        train,
        val,
        feature_columns=["close", "volume"],
        target_column=None,
        date_column="date",
    )
    assert res["overall_passed"] is True
