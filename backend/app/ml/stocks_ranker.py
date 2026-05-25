"""Cross-sectional LightGBM ranker for the stock universe.

A single *global* regressor is trained on the panel ``(date, ticker)`` against
forward log-returns. At inference time we score every active stock on the latest
trading day and rank cross-sectionally; downstream code converts that ranking into
a top-K portfolio with sector caps (see ``portfolio_backtest.py``).

Why a single global model instead of one model per ticker?
- The relative-value alpha lives in *cross-sectional* signals (sector-relative
  z-scores, momentum vs SPY) — those are most usefully learned across the entire
  panel.
- Per-ticker models for ~500 names overfits badly with only 5y of daily data.
- A global model also lets us deploy a single artifact and run inference for the
  whole universe in one ``predict`` call.

Walk-forward
------------
- Train window: 504 trading days (~2y)
- Validation window: 126 trading days (~6mo)
- Step: 126 trading days (non-overlapping validation)
- Rolling (not anchored) — financial regimes shift, so we don't want a 2010 bar
  influencing a 2025 prediction.

Metrics
-------
For each fold we compute per-day cross-sectional Spearman correlation between
predicted score and realised forward return, then average across days:
- ``ic``: information coefficient (Spearman, scores vs realised returns)
- ``rank_ic``: same but on rank-normalised inputs (robust to outliers)
- ``top_minus_bottom``: equal-weighted return spread of top decile minus bottom
  decile per day, averaged — a quick economic-significance check.

These get persisted to ``model_runs`` with ``asset_class='stock'`` (re-using the
existing schema columns: ``oos_auc`` stores IC, ``oos_precision`` stores rank IC,
``oos_recall`` stores top-minus-bottom, ``brier_score`` stores MAE — keeps the
schema additive-free; the API layer translates labels for the UI).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import spearmanr

from app.ml.features_stocks import (
    NON_FEATURE_COLS,
    split_features_targets,
    stock_feature_columns,
)

LOGGER = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

PANEL_KEY = "PANEL"
DEFAULT_TRAIN_DAYS = 504
DEFAULT_VAL_DAYS = 126
DEFAULT_STEP_DAYS = 126
DEFAULT_MIN_OBS_PER_DAY = 30


def stocks_artifact_path(horizon: str) -> Path:
    return MODEL_DIR / f"stocks_panel__{horizon}.joblib"


@dataclass(frozen=True)
class FoldMetrics:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    n_train: int
    n_val: int
    ic: float
    rank_ic: float
    top_minus_bottom: float
    mae: float


def _default_lgbm_params() -> dict[str, Any]:
    return {
        "objective": "regression",
        "n_estimators": 600,
        "learning_rate": 0.04,
        "num_leaves": 63,
        "max_depth": -1,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 0.2,
        "random_state": 42,
        "verbosity": -1,
        "n_jobs": -1,
    }


def _walk_forward_panel_splits(
    panel_dates: pd.DatetimeIndex,
    train_days: int,
    val_days: int,
    step_days: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Return [(train_start, train_end, val_start, val_end), ...] in chronological order."""
    unique_dates = pd.DatetimeIndex(panel_dates.unique()).sort_values()
    if len(unique_dates) < train_days + val_days:
        return []
    splits: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    start_idx = 0
    while True:
        train_end_idx = start_idx + train_days
        val_end_idx = train_end_idx + val_days
        if val_end_idx > len(unique_dates):
            break
        train_start = unique_dates[start_idx]
        train_end = unique_dates[train_end_idx - 1]
        val_start = unique_dates[train_end_idx]
        val_end = unique_dates[val_end_idx - 1]
        splits.append((train_start, train_end, val_start, val_end))
        start_idx += step_days
    return splits


def _per_day_spearman(scores: np.ndarray, returns: np.ndarray, dates: np.ndarray,
                     min_obs: int = DEFAULT_MIN_OBS_PER_DAY) -> tuple[float, float]:
    """Average daily Spearman + rank-Spearman across the validation window."""
    out_ic: list[float] = []
    out_rank_ic: list[float] = []
    for day, idx in pd.Series(np.arange(len(dates))).groupby(dates).groups.items():
        if len(idx) < min_obs:
            continue
        s = scores[idx]
        r = returns[idx]
        if np.unique(s).size < 3 or np.unique(r).size < 3:
            continue
        rho, _ = spearmanr(s, r)
        if np.isfinite(rho):
            out_ic.append(float(rho))
        rho_r, _ = spearmanr(pd.Series(s).rank().to_numpy(), pd.Series(r).rank().to_numpy())
        if np.isfinite(rho_r):
            out_rank_ic.append(float(rho_r))
    ic = float(np.mean(out_ic)) if out_ic else 0.0
    rank_ic = float(np.mean(out_rank_ic)) if out_rank_ic else 0.0
    return ic, rank_ic


def _per_day_top_minus_bottom(
    scores: np.ndarray, returns: np.ndarray, dates: np.ndarray, decile: float = 0.1
) -> float:
    diffs: list[float] = []
    for _, idx in pd.Series(np.arange(len(dates))).groupby(dates).groups.items():
        if len(idx) < int(1 / decile) * 2:
            continue
        s = scores[idx]
        r = returns[idx]
        order = np.argsort(s)
        cut = max(1, int(len(idx) * decile))
        bottom_mean = float(np.mean(r[order[:cut]]))
        top_mean = float(np.mean(r[order[-cut:]]))
        diffs.append(top_mean - bottom_mean)
    return float(np.mean(diffs)) if diffs else 0.0


def train_walk_forward(
    panel_feats: pd.DataFrame,
    target_horizon: int = 5,
    *,
    train_days: int = DEFAULT_TRAIN_DAYS,
    val_days: int = DEFAULT_VAL_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
    params: dict[str, Any] | None = None,
) -> tuple[list[FoldMetrics], list[dict[str, Any]], LGBMRegressor | None, list[str]]:
    """Walk-forward panel training. Returns (fold_metrics, oos_rows, final_model, feature_cols).

    - ``oos_rows`` is shaped for ``OosPrediction``: one row per (ticker, date, fold).
    - ``final_model`` is fit on the *last* train+val window combined, ready to deploy.
    """
    target_col = f"target_fwd_return_{target_horizon}d"
    if target_col not in panel_feats.columns:
        raise KeyError(f"Missing target column '{target_col}'.")

    work = panel_feats.dropna(subset=[target_col]).copy()
    if work.empty:
        return [], [], None, []

    work["date"] = pd.to_datetime(work["date"])
    feature_cols = stock_feature_columns(work)
    work[feature_cols] = work[feature_cols].astype(float).fillna(0.0)

    splits = _walk_forward_panel_splits(
        pd.DatetimeIndex(work["date"]), train_days, val_days, step_days
    )
    if not splits:
        LOGGER.warning("Insufficient data for walk-forward (rows=%d).", len(work))
        return [], [], None, feature_cols

    fold_metrics: list[FoldMetrics] = []
    oos_rows: list[dict[str, Any]] = []
    lgb_params = params or _default_lgbm_params()

    last_train_start: pd.Timestamp | None = None
    last_val_end: pd.Timestamp | None = None

    for fold_idx, (train_start, train_end, val_start, val_end) in enumerate(splits, start=1):
        train_mask = (work["date"] >= train_start) & (work["date"] <= train_end)
        val_mask = (work["date"] >= val_start) & (work["date"] <= val_end)
        train_df = work[train_mask]
        val_df = work[val_mask]
        if train_df.empty or val_df.empty:
            continue

        X_train = train_df[feature_cols].astype(np.float64).fillna(0.0)
        y_train = train_df[target_col].to_numpy(dtype=np.float64)
        X_val = val_df[feature_cols].astype(np.float64).fillna(0.0)
        y_val = val_df[target_col].to_numpy(dtype=np.float64)

        model = LGBMRegressor(**lgb_params)
        # Pass DataFrames so LightGBM keeps the column names consistent between
        # ``fit`` and ``predict`` (else sklearn raises a ``X does not have valid
        # feature names`` warning at inference time).
        model.fit(X_train, y_train)

        preds = model.predict(X_val)
        dates_arr = val_df["date"].to_numpy()
        ic, rank_ic = _per_day_spearman(preds, y_val, dates_arr)
        spread = _per_day_top_minus_bottom(preds, y_val, dates_arr)
        mae = float(np.mean(np.abs(preds - y_val)))

        fold_metrics.append(
            FoldMetrics(
                fold=fold_idx,
                train_start=train_start,
                train_end=train_end,
                val_start=val_start,
                val_end=val_end,
                n_train=int(len(train_df)),
                n_val=int(len(val_df)),
                ic=ic,
                rank_ic=rank_ic,
                top_minus_bottom=spread,
                mae=mae,
            )
        )

        val_iter = zip(
            val_df["date"].tolist(),
            val_df["ticker"].tolist(),
            y_val.tolist(),
            preds.tolist(),
        )
        for stamp, ticker, y_true, y_pred in val_iter:
            d = pd.Timestamp(stamp).date()
            oos_rows.append(
                {
                    "ticker": str(ticker),
                    "horizon": f"{target_horizon}d",
                    "asset_class": "stock",
                    "date": d,
                    "fold": fold_idx,
                    # ``OosPrediction.y_true`` is an INT column (designed for the
                    # classification path). For the regression panel we store the
                    # sign of the realised return as a coarse outcome and persist
                    # the continuous prediction in ``y_prob``. Downstream metrics
                    # are computed from the continuous score regardless.
                    "y_true": int(1 if y_true > 0 else 0),
                    "y_prob": float(y_pred),
                }
            )
        last_train_start = train_start
        last_val_end = val_end

    final_model: LGBMRegressor | None = None
    if last_train_start is not None and last_val_end is not None:
        # Refit on the most recent (train + val) window for production inference.
        recent_mask = (work["date"] >= last_train_start) & (work["date"] <= last_val_end)
        recent = work[recent_mask]
        X_full = recent[feature_cols].astype(np.float64).fillna(0.0)
        y_full = recent[target_col].to_numpy(dtype=np.float64)
        final_model = LGBMRegressor(**lgb_params)
        final_model.fit(X_full, y_full)
        payload = {
            "model": final_model,
            "feature_cols": feature_cols,
            "target_horizon": target_horizon,
            "trained_at": datetime.now(tz=UTC).isoformat(),
            "n_rows_fit": int(len(recent)),
        }
        joblib.dump(payload, stocks_artifact_path(f"{target_horizon}d"))
        LOGGER.info(
            "Persisted stock panel artifact for horizon=%dd (rows=%d, folds=%d)",
            target_horizon,
            len(recent),
            len(fold_metrics),
        )

    return fold_metrics, oos_rows, final_model, feature_cols


def fold_metrics_to_model_runs(
    metrics: Iterable[FoldMetrics],
    horizon: str,
) -> list[dict[str, Any]]:
    """Adapt ``FoldMetrics`` into ``ModelRun`` row dicts. Re-uses existing columns:

        oos_auc       -> Spearman IC
        oos_precision -> Rank IC
        oos_recall    -> Top-decile minus bottom-decile spread
        brier_score   -> MAE
    """
    trained_at = datetime.now(tz=UTC)
    rows: list[dict[str, Any]] = []
    for m in metrics:
        rows.append(
            {
                "ticker": PANEL_KEY,
                "horizon": horizon,
                "asset_class": "stock",
                "trained_at": trained_at,
                "oos_auc": float(m.ic),
                "oos_precision": float(m.rank_ic),
                "oos_recall": float(m.top_minus_bottom),
                "brier_score": float(m.mae),
                "fold": int(m.fold),
            }
        )
    return rows


def load_stocks_bundle(horizon: str) -> dict[str, Any] | None:
    path = stocks_artifact_path(horizon)
    if not path.exists():
        return None
    return joblib.load(path)


def score_latest(
    panel_feats: pd.DataFrame,
    bundle: dict[str, Any],
) -> pd.DataFrame:
    """Score the most recent date in ``panel_feats`` with the persisted ranker.

    Returns a DataFrame with ``[date, ticker, sector, close, score]`` for the
    latest date only.
    """
    if bundle is None or panel_feats is None or panel_feats.empty:
        return pd.DataFrame(columns=["date", "ticker", "sector", "close", "score"])

    model = bundle.get("model")
    feature_cols = list(bundle.get("feature_cols") or [])
    if model is None or not feature_cols:
        return pd.DataFrame(columns=["date", "ticker", "sector", "close", "score"])

    work = panel_feats.copy()
    work["date"] = pd.to_datetime(work["date"])
    latest_date = work["date"].max()
    latest = work[work["date"] == latest_date].copy()
    if latest.empty:
        return pd.DataFrame(columns=["date", "ticker", "sector", "close", "score"])

    missing = [c for c in feature_cols if c not in latest.columns]
    for c in missing:
        latest[c] = 0.0
    X = latest[feature_cols].astype(float).fillna(0.0)
    scores = model.predict(X)

    out = latest[["date", "ticker", "sector", "close"]].copy()
    out["score"] = scores.astype(float)
    out = out.sort_values("score", ascending=False).reset_index(drop=True)
    return out


def rank_and_apply_sector_caps(
    scored: pd.DataFrame,
    *,
    top_k: int = 25,
    max_per_sector: int | None = 5,
) -> pd.DataFrame:
    """Given a scored frame (one row per stock), assign cross-sectional ranks and
    flag the top-K names with per-sector caps applied. Returns the frame with
    ``rank`` and ``in_topk`` columns added (sorted by score desc).
    """
    if scored is None or scored.empty:
        return scored.copy() if scored is not None else scored
    df = scored.sort_values("score", ascending=False).reset_index(drop=True).copy()
    df["rank"] = np.arange(1, len(df) + 1)

    keep_flag = np.zeros(len(df), dtype=bool)
    sector_taken: dict[str, int] = {}
    selected = 0
    for i, row in df.iterrows():
        if selected >= top_k:
            break
        sector = str(row.get("sector") or "Unknown")
        if max_per_sector is not None and sector_taken.get(sector, 0) >= max_per_sector:
            continue
        keep_flag[i] = True
        sector_taken[sector] = sector_taken.get(sector, 0) + 1
        selected += 1

    df["in_topk"] = keep_flag
    return df
