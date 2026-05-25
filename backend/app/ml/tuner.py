"""Optuna hyperparameter search helpers for base learners."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import numpy as np
import optuna
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sqlalchemy.ext.asyncio import AsyncSession
from xgboost import XGBClassifier

from app.db.operations import upsert_hyperparams
from app.ml.features import training_feature_columns
from app.ml.trainer_support import TARGET_MAP

optuna.logging.set_verbosity(optuna.logging.WARNING)


def tune_xgb(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_trials: int = 20,
    random_state: int = 42,
) -> dict[str, Any]:
    scale = float(np.sum(y_train == 0) / max(1, int(np.sum(y_train == 1))))

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }

        clf = XGBClassifier(
            **params,
            random_state=random_state,
            eval_metric="auc",
            verbosity=0,
            n_jobs=-1,
            scale_pos_weight=scale,
        )
        scores = cross_val_score(
            clf,
            X_train,
            y_train,
            cv=TimeSeriesSplit(n_splits=5),
            scoring="roc_auc",
            n_jobs=-1,
        )
        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=int(n_trials), show_progress_bar=False)
    return study.best_params


def tune_lgbm(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_trials: int = 20,
    random_state: int = 42,
) -> dict[str, Any]:
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }

        clf = LGBMClassifier(
            **params,
            random_state=random_state,
            verbosity=-1,
            n_jobs=-1,
            class_weight="balanced",
        )

        scores = cross_val_score(
            clf,
            X_train,
            y_train,
            cv=TimeSeriesSplit(n_splits=5),
            scoring="roc_auc",
            n_jobs=-1,
        )

        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=int(n_trials), show_progress_bar=False)

    return study.best_params


def default_xgb_params() -> dict[str, Any]:
    return {
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 4,
        "reg_alpha": 1e-3,
        "reg_lambda": 1.0,
    }


def default_lgb_params() -> dict[str, Any]:
    return {
        "n_estimators": 400,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_alpha": 1e-3,
        "reg_lambda": 1.0,
    }


def numpy_xy_from_frame(frame: pd.DataFrame, horizon: str, min_rows: int = 200) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (X, y) arrays for tuning a single horizon, or None if insufficient clean rows."""
    target_column = TARGET_MAP[horizon]
    feature_cols = training_feature_columns(frame)
    cols = [*feature_cols, target_column]
    if target_column not in frame.columns:
        return None
    table = frame[cols].replace([np.inf, -np.inf], np.nan).dropna(how="any")
    if len(table) < min_rows:
        return None
    x_matrix = table[feature_cols].astype(float).values
    y_vector = table[target_column].astype(int).values.astype(int)
    return x_matrix, y_vector


async def optimize_and_store_horizon(
    session: AsyncSession,
    ticker: str,
    horizon: str,
    frame: pd.DataFrame,
    *,
    n_trials: int = 12,
) -> bool:
    """Run Optuna for XGB and LGBM in worker threads and persist rows to ``model_hyperparams``."""
    sample = numpy_xy_from_frame(frame, horizon)
    if sample is None:
        return False
    x_np, y_np = sample

    best_xgb = await asyncio.to_thread(tune_xgb, x_np, y_np, n_trials)
    best_lgb = await asyncio.to_thread(tune_lgbm, x_np, y_np, n_trials)
    stamped = datetime.now(tz=UTC)

    await upsert_hyperparams(
        session,
        {
            "ticker": ticker,
            "horizon": horizon,
            "model_type": "xgb",
            "params_json": dict(best_xgb),
            "tuned_at": stamped,
        },
    )
    await upsert_hyperparams(
        session,
        {
            "ticker": ticker,
            "horizon": horizon,
            "model_type": "lgbm",
            "params_json": dict(best_lgb),
            "tuned_at": stamped,
        },
    )
    return True
