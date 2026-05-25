"""Time-series data quality + leakage guards for walk-forward training.

Originally drafted in the ``ML-Trading`` repo. Promoted into the commodity-advisor
codebase because the cross-sectional stock ranker depends on identical guarantees:
- no temporal overlap between train/validation panels,
- targets are forward-looking (NaNs concentrated at the tail),
- feature distributions don't drift catastrophically across folds.

These checks are CI-friendly: they return a dict that callers can assert against.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)


def check_temporal_separation(
    train: pd.DataFrame,
    val: pd.DataFrame,
    date_column: str = "date",
) -> dict[str, Any]:
    """Verify train ends strictly before val starts."""
    checks: dict[str, Any] = {"passed": True, "issues": [], "warnings": []}
    if date_column not in train.columns or date_column not in val.columns:
        checks["passed"] = False
        checks["issues"].append(f"Missing date column '{date_column}'.")
        return checks

    train_dates = pd.to_datetime(train[date_column])
    val_dates = pd.to_datetime(val[date_column])
    train_max = train_dates.max()
    val_min = val_dates.min()

    if train_max >= val_min:
        checks["passed"] = False
        checks["issues"].append(
            f"Temporal overlap: train_max={train_max} >= val_min={val_min}"
        )

    if not train_dates.is_monotonic_increasing:
        checks["warnings"].append("Training panel is not sorted by date.")
    if not val_dates.is_monotonic_increasing:
        checks["warnings"].append("Validation panel is not sorted by date.")

    return checks


def check_no_infinite_features(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    label: str = "train",
) -> dict[str, Any]:
    bad: list[str] = []
    for col in feature_columns:
        if col not in frame.columns:
            continue
        arr = frame[col].to_numpy(dtype="float64", copy=False)
        if np.isinf(arr).any():
            bad.append(col)
    return {
        "passed": not bad,
        "label": label,
        "infinite_features": bad,
    }


def check_target_alignment(
    frame: pd.DataFrame,
    target_column: str,
    forward_days: int,
) -> dict[str, Any]:
    """Forward-looking targets should have ~forward_days NaNs at the tail per ticker."""
    checks: dict[str, Any] = {"passed": True, "issues": [], "warnings": []}
    if target_column not in frame.columns:
        checks["passed"] = False
        checks["issues"].append(f"Missing target column '{target_column}'.")
        return checks

    nan_total = int(frame[target_column].isna().sum())
    if nan_total == 0:
        checks["warnings"].append(
            f"No NaNs in '{target_column}'. Expected ~{forward_days} per ticker at the tail."
        )
    return checks


def check_distribution_drift(
    train: pd.DataFrame,
    val: pd.DataFrame,
    feature_columns: Sequence[str],
    sigma_threshold: float = 3.0,
) -> dict[str, Any]:
    """Flag features whose validation mean is >sigma_threshold train-std away."""
    out: dict[str, Any] = {"passed": True, "warnings": [], "stats": {}}
    for col in feature_columns:
        if col not in train.columns or col not in val.columns:
            continue
        t = train[col].dropna()
        v = val[col].dropna()
        if t.empty or v.empty:
            continue
        t_std = float(t.std())
        if t_std <= 0:
            continue
        shift = abs(float(v.mean()) - float(t.mean())) / t_std
        out["stats"][col] = {
            "train_mean": float(t.mean()),
            "train_std": t_std,
            "val_mean": float(v.mean()),
            "drift_sigmas": shift,
        }
        if shift > sigma_threshold:
            out["warnings"].append(f"'{col}' drift = {shift:.2f}σ")
    return out


def run_all_checks(
    train: pd.DataFrame,
    val: pd.DataFrame,
    feature_columns: Sequence[str],
    target_column: str | None = None,
    forward_days: int = 5,
    date_column: str = "date",
) -> dict[str, Any]:
    """Top-level helper used by tests + the training pipeline."""
    results: dict[str, Any] = {"overall_passed": True}

    sep = check_temporal_separation(train, val, date_column)
    results["temporal_separation"] = sep
    if not sep["passed"]:
        results["overall_passed"] = False

    inf_train = check_no_infinite_features(train, feature_columns, label="train")
    inf_val = check_no_infinite_features(val, feature_columns, label="val")
    results["infinite_features_train"] = inf_train
    results["infinite_features_val"] = inf_val
    if not inf_train["passed"] or not inf_val["passed"]:
        results["overall_passed"] = False

    if target_column is not None:
        results["target_alignment"] = check_target_alignment(
            pd.concat([train, val], ignore_index=True),
            target_column=target_column,
            forward_days=forward_days,
        )

    results["distribution_drift"] = check_distribution_drift(train, val, feature_columns)
    return results
