"""Multi-horizon inference from persisted calibrated models."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap

from app.constants import COMMODITIES, REGIME_LABELS
from app.ml.consensus_thresh import HORIZON_PROB_THRESHOLDS
from app.ml.trainer_support import artifact_path
from app.ml.features import training_feature_columns
from app.ml.sizer import kelly_position_size

logger = logging.getLogger(__name__)

def load_bundle(ticker: str, horizon: str) -> dict[str, Any] | None:
    path = artifact_path(ticker, horizon)
    if not path.exists():
        return None
    return joblib.load(path)

def _feature_matrix(bundle: dict[str, Any], row: pd.Series) -> tuple[np.ndarray, list[str]]:
    cols = list(bundle.get("feature_cols", []))
    if not cols:
        tmp = row.to_frame().T
        cols = training_feature_columns(tmp)
    ordered = row.reindex(cols).astype(float).values.reshape(1, -1)
    return ordered, cols

def _positives(model: Any, matrix: np.ndarray) -> float:
    prob_table = model.predict_proba(matrix)
    return float(prob_table[0][1])

def _shap_rows(bundle: dict[str, Any], matrix: np.ndarray, columns: list[str]) -> list[dict[str, float]]:
    model = bundle.get("model")
    if model is None:
        return []
    tree = None
    try:
        cal_list = getattr(model, "calibrated_classifiers_", None)
        if cal_list is None:
            return []
        first = cal_list[0]
        stack = getattr(first, "estimator", None)
        if stack is None:
            return []
        named = getattr(stack, "named_estimators_", {})
        tree = named.get("xgb")
    except Exception as exc:
        logger.debug("SHAP traversal failed: %s", exc)
        return []
    if tree is None:
        return []
    try:
        explainer = shap.TreeExplainer(tree)
        values = explainer.shap_values(matrix)
        shaped = np.array(values)
        shaped = shaped.reshape(matrix.shape)
        pairs = sorted(zip(columns, shaped[0].tolist()), key=lambda item: abs(item[1]), reverse=True)
        trimmed = pairs[:10]
        rows = [{"feature": name, "importance": float(weight)} for name, weight in trimmed]
        return rows
    except Exception as exc:
        logger.debug("SHAP explain failed: %s", exc)
        return []

def _load_regime_bundle(ticker: str, horizon: str, regime_k: int) -> dict[str, Any] | None:
    base = artifact_path(ticker, horizon)
    path = base.parent / f"{base.stem}__regime{regime_k}.joblib"
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def build_signal_payload(
    ticker: str,
    _frame: pd.DataFrame,
    latest_row: pd.Series,
    regime_label_value: float,
    regime_confidence_value: float,
    final_price: float,
    sentiment_snapshot: dict[str, Any],
    stats_block: dict[str, Any],
) -> dict[str, Any]:
    bundles = {"5d": load_bundle(ticker, "5d"), "10d": load_bundle(ticker, "10d"), "21d": load_bundle(ticker, "21d")}
    current_regime = int(float(regime_label_value))
    probs: dict[str, float] = {}
    shap_union: list[dict[str, float]] = []
    for horizon, bundle in bundles.items():
        if bundle is None:
            probs[horizon] = 0.0
            continue
        matrix, cols = _feature_matrix(bundle, latest_row)
        try:
            global_prob = _positives(bundle["model"], matrix)
        except Exception:
            global_prob = 0.0
        # Blend with regime sub-model if available and trained on enough samples
        regime_bundle = _load_regime_bundle(ticker, horizon, current_regime)
        if regime_bundle is not None and regime_bundle.get("n_samples", 0) >= 30:
            try:
                r_matrix, _ = _feature_matrix(regime_bundle, latest_row)
                regime_prob = _positives(regime_bundle["model"], r_matrix)
                probs[horizon] = round(0.6 * regime_prob + 0.4 * global_prob, 4)
            except Exception:
                probs[horizon] = global_prob
        else:
            probs[horizon] = global_prob
        shap_piece = _shap_rows(bundle, matrix, cols)
        if shap_piece:
            shap_union = shap_piece
    avg_score = sum(probs.values()) / max(1, len(probs))
    gate_regime_ok = float(regime_label_value) != 2.0
    cond5 = probs["5d"] >= HORIZON_PROB_THRESHOLDS["5d"]
    cond10 = probs["10d"] >= HORIZON_PROB_THRESHOLDS["10d"]
    cond21 = probs["21d"] >= HORIZON_PROB_THRESHOLDS["21d"]
    consensus_flag = bool(cond5 and cond10 and cond21 and gate_regime_ok)
    label = "BUY" if consensus_flag else "HOLD"
    win_rate = float(stats_block.get("win_rate", 0.0))
    avg_win = float(stats_block.get("avg_win_pct", 0.0))
    avg_loss = float(stats_block.get("avg_loss_pct", 0.0))
    kelly_fraction = kelly_position_size(win_rate, avg_win, avg_loss) if label == "BUY" else 0.0

    # Expected return: probability-weighted outcome using backtest avg win/loss
    p_up = avg_score
    expected_return_pct = round(p_up * avg_win - (1.0 - p_up) * avg_loss, 4)
    # Downside risk: loss side of distribution at 1-sigma confidence
    downside_risk_pct = round(avg_loss * (1.0 - p_up), 4)

    friendly = COMMODITIES.get(ticker, ticker)
    regime_index = int(float(regime_label_value))
    regime_text = REGIME_LABELS.get(regime_index, "Unknown")
    action_text = f"Buy {ticker} futures or related ETF. Target hold near 21-30 trading days."
    payload = {
        "ticker": ticker,
        "name": friendly,
        "signal": label,
        "avg_confidence": round(avg_score, 4),
        "confidence_5d": round(probs["5d"], 4),
        "confidence_10d": round(probs["10d"], 4),
        "confidence_21d": round(probs["21d"], 4),
        "current_price": float(final_price),
        "regime": regime_index,
        "regime_label": regime_text,
        "regime_confidence": float(regime_confidence_value),
        "consensus": consensus_flag,
        "position_size_pct": kelly_fraction,
        "expected_return_pct": expected_return_pct,
        "downside_risk_pct": downside_risk_pct,
        "suggested_action": action_text,
        "sentiment": sentiment_snapshot,
        "backtest": stats_block,
        "shap_features": shap_union,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "correlation_filtered": False,
    }
    return payload
