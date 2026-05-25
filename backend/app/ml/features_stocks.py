"""Cross-sectional feature engineering for the stock universe.

Pipeline:
1. Reuse the per-ticker technical indicator block from ``app.ml.features``
   (RSI, MACD, Bollinger, ATR, OBV, Parkinson/Garman-Klass vol, etc.).
2. Layer in benchmark (SPY) cross-asset features:
   - rolling correlation,
   - relative return vs SPY at 1d / 5d / 20d,
   - market regime (SPY above its 200-day SMA).
3. Layer in sector-relative cross-sectional z-scores: each day, for a chosen
   set of features, subtract the sector mean and divide by sector std. This is
   the key edge for a top-K ranker — absolute momentum is much less informative
   than momentum *relative to peers* in the same GICS sector.
4. Append forward-return targets (5d / 21d log returns).

All operations are vectorised; the panel for 500 names × 5 years runs in a few
seconds on a modern laptop.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from app.ml.features import attach_seasonality, build_price_features

LOGGER = logging.getLogger(__name__)

# Features that benefit most from sector-relative normalization.
SECTOR_RELATIVE_FEATURES: tuple[str, ...] = (
    "log_return_5d",
    "log_return_10d",
    "log_return_21d",
    "RSI_14",
    "MACD_histogram",
    "BB_position",
    "Price_vs_52w_high",
    "realized_vol_21d",
    "volume_zscore",
    "OBV_slope",
)

DEFAULT_FORWARD_HORIZONS: tuple[int, ...] = (5, 21)


def _add_benchmark_features(
    feats: pd.DataFrame,
    close: pd.Series,
    benchmark: pd.Series,
) -> pd.DataFrame:
    """Attach SPY (benchmark) cross-asset features in place."""
    if benchmark is None or benchmark.empty:
        feats["spy_corr_20d"] = np.nan
        feats["spy_rel_return_1d"] = np.nan
        feats["spy_rel_return_5d"] = np.nan
        feats["spy_rel_return_21d"] = np.nan
        feats["spy_regime_bull"] = 0.0
        return feats

    bench = benchmark.reindex(feats.index).astype(float).ffill()
    bench_lr1 = np.log(bench / bench.shift(1)).replace([np.inf, -np.inf], np.nan)
    stock_lr1 = np.log(close.reindex(feats.index).astype(float) / close.reindex(feats.index).astype(float).shift(1))
    stock_lr1 = stock_lr1.replace([np.inf, -np.inf], np.nan)

    feats["spy_corr_20d"] = stock_lr1.rolling(20, min_periods=10).corr(bench_lr1)
    for window, label in ((1, "1d"), (5, "5d"), (21, "21d")):
        stock_ret = np.log(close / close.shift(window)).replace([np.inf, -np.inf], np.nan)
        bench_ret = np.log(bench / bench.shift(window)).replace([np.inf, -np.inf], np.nan)
        feats[f"spy_rel_return_{label}"] = stock_ret - bench_ret

    bench_sma200 = bench.rolling(200, min_periods=50).mean()
    feats["spy_regime_bull"] = (bench > bench_sma200).astype(float)
    return feats


def _add_forward_targets(feats: pd.DataFrame, close: pd.Series, horizons: Iterable[int]) -> pd.DataFrame:
    c = close.reindex(feats.index).astype(float)
    for h in horizons:
        feats[f"target_fwd_return_{h}d"] = np.log(c.shift(-h) / c).replace(
            [np.inf, -np.inf], np.nan
        )
    return feats


def _build_per_ticker(
    sub: pd.DataFrame,
    ticker: str,
    sector: str,
    benchmark: pd.Series,
    horizons: Iterable[int],
) -> pd.DataFrame:
    px = sub.set_index("date").sort_index()
    if px.empty or len(px) < 60:
        return pd.DataFrame()

    feats = build_price_features(px)
    attach_seasonality(feats.index, feats)

    feats = _add_benchmark_features(feats, px["close"], benchmark)
    feats = _add_forward_targets(feats, px["close"], horizons)

    feats["ticker"] = ticker
    feats["sector"] = sector or "Unknown"
    feats["close"] = px["close"].astype(float).values
    return feats.reset_index().rename(columns={"index": "date"})


def _add_sector_relative_zscores(
    panel: pd.DataFrame,
    features: Sequence[str] = SECTOR_RELATIVE_FEATURES,
    sector_col: str = "sector",
    date_col: str = "date",
) -> pd.DataFrame:
    """Append ``<feat>_sector_z`` columns: cross-sectional z-score within sector & date."""
    out = panel.copy()
    work_cols = [c for c in features if c in out.columns]
    if not work_cols:
        return out

    group_keys = [date_col, sector_col]
    grouped = out.groupby(group_keys, sort=False, observed=True)[work_cols]
    means = grouped.transform("mean")
    stds = grouped.transform("std").replace(0, np.nan)
    z = (out[work_cols] - means) / stds
    z = z.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    z.columns = [f"{c}_sector_z" for c in work_cols]
    return pd.concat([out, z], axis=1)


_SENTIMENT_FEATURE_MAP = {
    "score_1d": "sent_score_1d",
    "score_3d": "sent_score_3d",
    "momentum": "sent_momentum",
    "volume": "sent_volume",
}


def _attach_sentiment(panel_feats: pd.DataFrame, sentiment: pd.DataFrame | None) -> pd.DataFrame:
    """Left-join sentiment per (ticker, date) and forward-fill within ticker.

    News flow is sparse — many stocks won't have a headline every trading day
    — so we ffill within each ticker (with a 5-day cap) and zero-fill anything
    still missing. Output columns are renamed to ``sent_*`` to keep the panel
    namespace tidy.
    """
    feature_cols = list(_SENTIMENT_FEATURE_MAP.values())
    if sentiment is None or sentiment.empty:
        for c in feature_cols:
            panel_feats[c] = 0.0
        return panel_feats

    sent = sentiment.copy()
    sent["date"] = pd.to_datetime(sent["date"])
    rename = {k: v for k, v in _SENTIMENT_FEATURE_MAP.items() if k in sent.columns}
    sent = sent.rename(columns=rename)
    keep = ["ticker", "date", *rename.values()]
    sent = sent[keep].drop_duplicates(["ticker", "date"], keep="last")

    panel_feats = panel_feats.merge(sent, on=["ticker", "date"], how="left", sort=False)

    # Forward-fill within ticker (cap at 5 sessions of carry-over).
    panel_feats = panel_feats.sort_values(["ticker", "date"]).reset_index(drop=True)
    for col in rename.values():
        panel_feats[col] = (
            panel_feats.groupby("ticker", observed=True)[col]
            .transform(lambda s: s.ffill(limit=5))
            .fillna(0.0)
        )
    # Ensure all four columns exist even if upstream is missing some.
    for c in feature_cols:
        if c not in panel_feats.columns:
            panel_feats[c] = 0.0
    return panel_feats


def build_stock_panel_features(
    panel: pd.DataFrame,
    benchmark: pd.Series,
    sector_map: dict[str, str],
    *,
    horizons: Iterable[int] = DEFAULT_FORWARD_HORIZONS,
    min_history_rows: int = 60,
    sentiment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Take the long-format stock OHLCV panel and produce a feature panel ready for
    the cross-sectional ranker.

    Returned columns include:
    - all technical indicators from ``build_price_features``,
    - seasonality columns (dow/month/woy sin-cos, month-end flags),
    - ``spy_corr_20d``, ``spy_rel_return_{1d,5d,21d}``, ``spy_regime_bull``,
    - sentiment features (``sent_score_1d``/``sent_score_3d``/``sent_momentum``/
      ``sent_volume``) when ``sentiment`` is provided,
    - sector-relative z-scores for the items in ``SECTOR_RELATIVE_FEATURES``,
    - ``target_fwd_return_5d``, ``target_fwd_return_21d`` (NaN at the panel tail),
    - identity columns ``ticker``, ``sector``, ``date``, ``close``.
    """
    if panel is None or panel.empty:
        return pd.DataFrame()

    required = {"date", "ticker", "open", "high", "low", "close", "volume"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Panel missing columns: {sorted(missing)}")

    if not isinstance(benchmark, pd.Series):
        raise TypeError("benchmark must be a pandas Series indexed by date.")

    pieces: list[pd.DataFrame] = []
    skipped = 0
    for ticker, sub in panel.groupby("ticker", sort=False):
        if len(sub) < min_history_rows:
            skipped += 1
            continue
        sector = sector_map.get(str(ticker), "Unknown")
        piece = _build_per_ticker(sub, str(ticker), sector, benchmark, horizons)
        if not piece.empty:
            pieces.append(piece)

    if not pieces:
        LOGGER.warning("No tickers produced features (skipped=%d).", skipped)
        return pd.DataFrame()

    panel_feats = pd.concat(pieces, ignore_index=True)
    panel_feats["date"] = pd.to_datetime(panel_feats["date"])

    panel_feats = _attach_sentiment(panel_feats, sentiment)
    panel_feats = _add_sector_relative_zscores(panel_feats)
    panel_feats = panel_feats.sort_values(["date", "ticker"]).reset_index(drop=True)

    if skipped:
        LOGGER.info("build_stock_panel_features: skipped %d short-history tickers.", skipped)
    return panel_feats


# ----------------------------------------------------------------------------
# Helpers for downstream training / ranking
# ----------------------------------------------------------------------------

NON_FEATURE_COLS = {
    "date",
    "ticker",
    "sector",
    "close",
    "open",
    "high",
    "low",
    "volume",
    "adj_close",
    "target_fwd_return_5d",
    "target_fwd_return_21d",
}


def stock_feature_columns(panel_feats: pd.DataFrame) -> list[str]:
    return [c for c in panel_feats.columns if c not in NON_FEATURE_COLS]


def split_features_targets(
    panel_feats: pd.DataFrame,
    target_horizon: int = 5,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Return (X, y, meta) where ``meta`` carries date/ticker/sector for downstream
    cross-sectional ranking and reporting. Rows with NaN target are dropped."""
    target_col = f"target_fwd_return_{target_horizon}d"
    if target_col not in panel_feats.columns:
        raise KeyError(f"Missing target column '{target_col}'.")
    keep = panel_feats[panel_feats[target_col].notna()].copy()
    feat_cols = stock_feature_columns(keep)
    X = keep[feat_cols].astype(float).fillna(0.0)
    y = keep[target_col].astype(float)
    meta = keep[["date", "ticker", "sector", "close"]].reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = y.reset_index(drop=True)
    return X, y, meta
