"""HMM regime detection (3-state) per commodity ticker."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

logger = logging.getLogger(__name__)

MODEL_ROOT = Path(__file__).resolve().parent / "models" / "regime"


def regime_artifact_path(ticker: str) -> Path:
    safe = ticker.replace("=", "_").replace("/", "_")
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    return MODEL_ROOT / f"{safe}.joblib"


META_SUFFIX = ".mapping.json"


def _build_state_mapping(
    states: np.ndarray,
    ret: np.ndarray,
    vol: np.ndarray,
) -> dict[int, int]:
    uniq = sorted({int(s) for s in np.unique(states)})
    if not uniq:
        return {}

    mean_vol = {u: float(np.nanmean(vol[states == u])) for u in uniq}
    mean_ret = {u: float(np.nanmean(ret[states == u])) for u in uniq}

    crisis = max(uniq, key=lambda u: mean_vol[u])
    others = [u for u in uniq if u != crisis]

    bull = uniq[0]
    bear = uniq[0]
    if len(others) >= 2:
        bull = max(others, key=lambda u: mean_ret[u])
        bear = min(others, key=lambda u: mean_ret[u])
    elif len(others) == 1:
        bull = bear = others[0]

    mapping: dict[int, int] = {int(bear): 0, int(bull): 1, int(crisis): 2}

    for u in uniq:
        mapping.setdefault(int(u), 1)

    return mapping


def fit_and_save_regime(ticker: str, df: pd.DataFrame) -> dict:
    """Train HMM on overlapping rows with required columns; save joblib + mapping json."""
    feats = df[["realized_vol_21d", "log_return_5d", "volume_zscore"]].astype(float)
    valid = feats.replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) < 500:
        logger.warning("Insufficient rows for HMM on %s (%s)", ticker, len(valid))

    X = valid.values
    model = GaussianHMM(
        n_components=3,
        covariance_type="full",
        n_iter=1000,
        random_state=42,
    )
    model.fit(X)

    states = model.predict(X)
    ret = df.reindex(valid.index)["log_return_5d"].astype(float).values
    vol = df.reindex(valid.index)["realized_vol_21d"].astype(float).values
    mapping = _build_state_mapping(np.asarray(states, dtype=int), ret, vol)

    canonical = np.vectorize(lambda s: mapping.get(int(s), int(s)))(states.astype(int))
    probs = model.predict_proba(X)

    out = {
        "model": model,
        "mapping": mapping,
        "trained_index": valid.index,
        "states_raw": states.astype(int),
        "states_canonical": canonical.astype(int),
        "state_probs": probs,
    }

    path = regime_artifact_path(ticker)
    joblib.dump({"model": model, "mapping": mapping}, path)
    with open(str(path) + META_SUFFIX, "w", encoding="utf-8") as fh:
        json.dump({"ticker": ticker, "mapping": {str(k): v for k, v in mapping.items()}}, fh)

    return out


def load_regime_bundle(ticker: str) -> dict | None:
    path = regime_artifact_path(ticker)
    if not path.exists():
        return None

    data = joblib.load(path)
    return data


def predict_regime_series(df: pd.DataFrame, bundle: dict | None) -> tuple[pd.Series, pd.Series]:
    if bundle is None:
        z = pd.Series(0.0, index=df.index)
        return z, z.astype(float)

    model: GaussianHMM = bundle["model"]
    mapping: dict[int, int] = bundle["mapping"]

    cols = ["realized_vol_21d", "log_return_5d", "volume_zscore"]
    feats = df[cols].astype(float).replace([np.inf, -np.inf], np.nan)
    idx = feats.dropna().index
    if len(idx) == 0:
        z = pd.Series(0.0, index=df.index)
        return z, z.astype(float)

    X = feats.loc[idx].values
    raw = model.predict(X)
    probs = model.predict_proba(X)
    conf = probs.max(axis=1)
    canon = np.vectorize(lambda s: int(mapping.get(int(s), int(s))))(raw.astype(int))

    label = pd.Series(canon, index=idx).reindex(df.index).ffill().fillna(0.0)

    confidence = pd.Series(conf.astype(float), index=idx).reindex(df.index).ffill().fillna(0.0)
    return label, confidence


async def train_regime_for_ticker(ticker: str, feats: pd.DataFrame) -> dict:
    return fit_and_save_regime(ticker, feats)


def ensure_regime_bundle(ticker: str) -> dict | None:
    return load_regime_bundle(ticker)
