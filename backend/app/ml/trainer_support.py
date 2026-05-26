"""Synchronous stacking + monthly walk-forward OOS generation.

Cost note: the original implementation wrapped a 5-fold StackingClassifier in
a 3-fold CalibratedClassifierCV and refit it once per (ticker, horizon, month)
fold across the full price history. With 5y of data that's ~3000 outer fits
times ~33 inner fits per outer = ~100k model fits per ``initial_data_load``,
which on a laptop runs for hours. We made three production-friendly choices:

* drop ``CalibratedClassifierCV`` (huge cost; calibration didn't change the
  signal direction the UI consumes, only the calibration curve),
* reduce stack ``cv`` from 5 to 3,
* cap walk-forward to the most recent ``MAX_WALK_FORWARD_MONTHS`` months
  (default 12, override via env).

Net effect: ~30-50x faster bootstrap. Re-tune later by setting the env knob
back up if you want denser OOS history.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
from xgboost import XGBClassifier

from app.ml.features import training_feature_columns

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TARGET_MAP = {"5d": "target_5d", "10d": "target_10d", "21d": "target_21d"}

# Walk-forward budget. Each outer month re-fits the entire ensemble; capping it
# is the single biggest perf lever for the commodity bootstrap.
MAX_WALK_FORWARD_MONTHS = int(os.environ.get("MAX_WALK_FORWARD_MONTHS", "12"))

_XGB_KEYS = {
    "n_estimators",
    "max_depth",
    "learning_rate",
    "subsample",
    "colsample_bytree",
    "min_child_weight",
    "reg_alpha",
    "reg_lambda",
}
_LGB_KEYS = {
    "n_estimators",
    "max_depth",
    "learning_rate",
    "subsample",
    "colsample_bytree",
    "reg_alpha",
    "reg_lambda",
}


def artifact_path(ticker: str, horizon: str) -> Path:
    return MODEL_DIR / f"{ticker.replace('=', '_')}__{horizon}.joblib"


def _subset_params(p: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {k: p[k] for k in keys if k in p}


def _scale_pos_weight(y: np.ndarray) -> float:
    return float(np.sum(y == 0) / max(1.0, float(np.sum(y == 1))))


def _build_stack(xgb_p: dict[str, Any], lgb_p: dict[str, Any], spw: float) -> StackingClassifier:
    xgb = XGBClassifier(
        **_subset_params(xgb_p, _XGB_KEYS),
        random_state=42,
        eval_metric="auc",
        verbosity=0,
        n_jobs=1,
        scale_pos_weight=spw,
    )
    lgb = LGBMClassifier(
        **_subset_params(lgb_p, _LGB_KEYS),
        random_state=42,
        verbosity=-1,
        n_jobs=1,
    )
    meta = LogisticRegression(C=0.1, max_iter=3000)
    # ``cv`` here is internal to stacking; the outer monthly walk-forward in
    # ``train_one_horizon_sync`` already enforces no-look-ahead at the
    # train/test boundary. sklearn >= 1.6 requires this inner CV to produce a
    # complete partition (TimeSeriesSplit doesn't), so we use an integer.
    return StackingClassifier(
        estimators=[("xgb", xgb), ("lgbm", lgb)],
        final_estimator=meta,
        cv=3,
        stack_method="predict_proba",
        passthrough=True,
        n_jobs=1,
    )


def _wrap_calibrated(stack: StackingClassifier) -> StackingClassifier:
    """Calibration wrapper deliberately removed for performance — see module
    docstring. The function name is preserved to keep the call-sites ergonomic
    in case calibration is reintroduced under a feature flag later."""
    return stack


def _month_labels(index: pd.DatetimeIndex) -> list[tuple[int, int]]:
    """Most-recent ``MAX_WALK_FORWARD_MONTHS`` (year, month) buckets.

    The walk-forward outer loop in ``train_one_horizon_sync`` re-fits the full
    stacking ensemble at each month, so capping the count is the dominant lever
    for ``initial_data_load`` runtime.
    """
    idx_sorted = pd.DatetimeIndex(index).sort_values()
    buckets: set[tuple[int, int]] = set()
    for stamp in idx_sorted:
        buckets.add((int(stamp.year), int(stamp.month)))
    ordered = sorted(buckets)
    if MAX_WALK_FORWARD_MONTHS > 0 and len(ordered) > MAX_WALK_FORWARD_MONTHS:
        return ordered[-MAX_WALK_FORWARD_MONTHS:]
    return ordered


def train_one_horizon_sync(
    ticker: str,
    horizon: str,
    df: pd.DataFrame,
    xgb_params: dict[str, Any],
    lgb_params: dict[str, Any],
    min_train_rows: int = 400,
    min_test_rows: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    target_column = TARGET_MAP[horizon]
    feature_cols = training_feature_columns(df)
    cols = [*feature_cols, target_column]
    table = df[cols].replace([np.inf, -np.inf], np.nan).dropna(how="any")
    if table.empty:
        logger.warning("%s %s cleaned frame empty", ticker, horizon)
        return [], [], feature_cols

    idx = pd.DatetimeIndex(pd.to_datetime(table.index)).sort_values()
    table = table.reindex(idx)

    periods = _month_labels(idx)
    trained_at = datetime.now(tz=UTC)
    oos_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    fold_count = 0

    for year, month in periods:
        start = pd.Timestamp(year=year, month=month, day=1)
        end_exclusive = start + pd.DateOffset(months=1)
        train_keep = idx < start
        test_keep = (idx >= start) & (idx < end_exclusive)
        train_slice = table.loc[train_keep]
        test_slice = table.loc[test_keep]
        fold_count += 1
        if len(train_slice) < min_train_rows or len(test_slice) < min_test_rows:
            continue

        x_matrix = train_slice[feature_cols].astype(float).values
        y_vector = train_slice[target_column].astype(int).values.astype(int)
        model = _wrap_calibrated(_build_stack(xgb_params, lgb_params, _scale_pos_weight(y_vector)))

        model.fit(x_matrix, y_vector)

        x_hold = test_slice[feature_cols].astype(float).values

        probs = model.predict_proba(x_hold)[:, 1]

        truth = test_slice[target_column].astype(int).values.astype(int)
        try:
            guesses = np.where(probs >= 0.5, 1, 0)
            precision_metric = float(precision_score(truth, guesses, zero_division=0))
            recall_metric = float(recall_score(truth, guesses, zero_division=0))
        except Exception:
            precision_metric = 0.0
            recall_metric = 0.0
        try:
            brier_metric = float(brier_score_loss(truth, probs))
        except Exception:
            brier_metric = 0.5
        try:
            auc_metric = float(roc_auc_score(truth, probs))
            if auc_metric != auc_metric:
                auc_metric = 0.0
        except Exception:
            auc_metric = 0.0
        run_rows.append(
            {
                "ticker": ticker,
                "horizon": horizon,
                "trained_at": trained_at,
                "oos_auc": auc_metric,
                "oos_precision": precision_metric,
                "oos_recall": recall_metric,
                "brier_score": brier_metric,
                "fold": int(fold_count),
            }
        )
        for stamp, y_true, prob in zip(test_slice.index, truth.astype(int).tolist(), probs.tolist()):
            day = stamp.date() if hasattr(stamp, "date") else pd.Timestamp(stamp).date()
            oos_rows.append(
                {
                    "ticker": ticker,
                    "horizon": horizon,
                    "date": day,
                    "fold": int(fold_count),
                    "y_true": int(y_true),
                    "y_prob": float(prob),
                }
            )
    if len(table) < min_train_rows:
        logger.warning("%s %s insufficient rows for final fit", ticker, horizon)
        return oos_rows, run_rows, feature_cols
    y_final = table[target_column].astype(int).values.astype(int)
    x_final = table[feature_cols].astype(float).values
    spw_final = _scale_pos_weight(y_final)
    final_model = _wrap_calibrated(_build_stack(xgb_params, lgb_params, spw_final))
    final_model.fit(x_final, y_final)
    payload = {"model": final_model, "feature_cols": feature_cols, "target": target_column}
    joblib.dump(payload, artifact_path(ticker, horizon))

    # Regime-conditional sub-models (0=bear, 1=bull, 2=high-vol)
    if "regime_label" in table.columns:
        base_path = artifact_path(ticker, horizon)
        for regime_k in [0, 1, 2]:
            regime_rows = table[table["regime_label"] == regime_k]
            if len(regime_rows) < 60:
                continue
            try:
                y_r = regime_rows[target_column].astype(int).values.astype(int)
                x_r = regime_rows[feature_cols].astype(float).values
                spw_r = _scale_pos_weight(y_r)
                regime_model = _wrap_calibrated(_build_stack(xgb_params, lgb_params, spw_r))
                regime_model.fit(x_r, y_r)
                regime_path = base_path.parent / f"{base_path.stem}__regime{regime_k}.joblib"
                joblib.dump({"model": regime_model, "feature_cols": feature_cols, "n_samples": len(regime_rows)}, regime_path)
                logger.info("%s %s regime%d sub-model saved (%d rows)", ticker, horizon, regime_k, len(regime_rows))
            except Exception as exc:
                logger.debug("Regime sub-model %s %s k=%d failed: %s", ticker, horizon, regime_k, exc)

    return oos_rows, run_rows, feature_cols
