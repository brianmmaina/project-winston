"""Feature engineering for tabular models (+ regime placeholders)."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

NON_FEATURE_COLUMNS = {
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "target_5d",
    "target_10d",
    "target_21d",
}


def training_feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(2, n // 3)).mean()


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=max(2, span // 2)).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    ma_up = up.rolling(period).mean()
    ma_down = down.rolling(period).mean().replace(0, np.nan)
    rs = ma_up / ma_down
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    parts = pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1)
    return parts.max(axis=1)


def build_price_features(px: pd.DataFrame) -> pd.DataFrame:
    close = px["close"].astype(float)
    high = px["high"].astype(float)
    low = px["low"].astype(float)
    open_ = px["open"].astype(float)
    volume = px["volume"].astype(float)

    lr1 = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    out = pd.DataFrame(index=px.index)
    out["log_return_1d"] = lr1
    out["log_return_5d"] = np.log(close / close.shift(5)).replace([np.inf, -np.inf], np.nan)
    out["log_return_10d"] = np.log(close / close.shift(10)).replace([np.inf, -np.inf], np.nan)
    out["log_return_21d"] = np.log(close / close.shift(21)).replace([np.inf, -np.inf], np.nan)

    for n in (10, 20, 50, 200):
        out[f"SMA_{n}"] = _sma(close, n)

    out["SMA_crossover_10_50"] = out["SMA_10"] / out["SMA_50"].replace(0, np.nan)
    out["SMA_crossover_50_200"] = out["SMA_50"] / out["SMA_200"].replace(0, np.nan)

    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    out["EMA_12"] = ema12
    out["EMA_26"] = ema26
    macd = ema12 - ema26
    out["MACD"] = macd
    out["MACD_signal"] = _ema(macd, 9)
    out["MACD_histogram"] = out["MACD"] - out["MACD_signal"]

    out["RSI_14"] = _rsi(close, 14)
    out["RSI_7"] = _rsi(close, 7)

    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    rng = (high14 - low14).replace(0, np.nan)
    st_k = ((close - low14) / rng * 100.0).replace([np.inf, -np.inf], np.nan).fillna(50.0)
    out["Stochastic_K_14"] = st_k
    out["Stochastic_D_3"] = out["Stochastic_K_14"].rolling(3).mean()

    out["Williams_R_14"] = (((high14 - close) / rng) * (-100.0)).replace([np.inf, -np.inf], np.nan).fillna(-50.0)

    tp = (high + low + close) / 3.0
    sma_tp = _sma(tp, 20)
    mad = (tp - sma_tp).abs().rolling(20).mean()
    out["CCI_20"] = ((tp - sma_tp) / (0.015 * mad.replace(0, np.nan))).fillna(0.0)

    mid20 = _sma(close, 20)
    std20 = close.rolling(20).std(ddof=0)
    bb_u = mid20 + 2 * std20
    bb_l = mid20 - 2 * std20
    den = (bb_u - bb_l).replace(0, np.nan)
    out["BB_position"] = ((close - bb_l) / den).clip(lower=-5, upper=5)
    out["BB_width"] = ((bb_u - bb_l) / mid20.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    roll_hi = close.rolling(252, min_periods=50).max()
    roll_lo = close.rolling(252, min_periods=50).min()
    out["Price_vs_52w_high"] = close / roll_hi.replace(0, np.nan)
    out["Price_vs_52w_low"] = close / roll_lo.replace(0, np.nan)

    tr = _true_range(high, low, close)
    out["ATR_14"] = tr.rolling(14).mean()
    out["ATR_ratio"] = out["ATR_14"] / close.replace(0, np.nan)

    rl21 = lr1.rolling(21).std(ddof=0) * np.sqrt(252)
    rl63 = lr1.rolling(63).std(ddof=0) * np.sqrt(252)
    out["realized_vol_21d"] = rl21
    out["realized_vol_63d"] = rl63
    out["vol_ratio"] = rl21 / rl63.replace(0, np.nan)

    hl = (np.log(high / low.replace(0, np.nan)) ** 2).replace([np.inf, -np.inf], np.nan)
    out["Parkinson_vol"] = np.sqrt(hl.rolling(21).mean() / (4.0 * np.log(2.0)))

    log_hl = np.log(high / low.replace(0, np.nan))
    log_co = np.log(close / open_.replace(0, np.nan))
    rs = (0.5 * log_hl**2) - (2 * np.log(2.0) - 1.0) * log_co**2
    out["garman_klass_vol"] = np.sqrt(rs.clip(lower=0.0).rolling(21).mean() * 252.0)

    obv_chg = pd.Series(
        np.where(close > close.shift(1), volume, np.where(close < close.shift(1), -volume, 0.0)),
        index=close.index,
    )
    out["OBV"] = obv_chg.fillna(0.0).cumsum()
    out["OBV_slope"] = ((out["OBV"] - out["OBV"].shift(5)) / 5.0).astype(float)

    vm30 = volume.rolling(30).mean()
    vs30 = volume.rolling(30).std(ddof=0).replace(0, np.nan)
    out["volume_zscore"] = (volume - vm30) / vs30.replace(0, np.nan)

    out["volume_trend"] = volume / volume.rolling(10).mean().replace(0, np.nan)

    return out


def attach_seasonality(idx: pd.DatetimeIndex, out: pd.DataFrame) -> None:
    TWO_PI = float(2.0 * np.pi)
    dow = idx.dayofweek.astype(float)
    out["dow_sin"] = np.sin(TWO_PI * dow / 5.0)
    out["dow_cos"] = np.cos(TWO_PI * dow / 5.0)

    month = idx.month.astype(float)
    out["month_sin"] = np.sin(TWO_PI * (month - 1.0) / 12.0)
    out["month_cos"] = np.cos(TWO_PI * (month - 1.0) / 12.0)

    woy = idx.isocalendar().week.astype(float)
    out["woy_sin"] = np.sin(TWO_PI * (woy - 1.0) / 52.0)
    out["woy_cos"] = np.cos(TWO_PI * (woy - 1.0) / 52.0)

    out["is_month_end"] = idx.is_month_end.astype(float)
    out["is_quarter_end"] = (idx.is_month_end & idx.month.isin([3, 6, 9, 12])).astype(float)


def merge_macro_sentiment_lagged(base: pd.DataFrame, macro: pd.DataFrame, sentiment: pd.DataFrame) -> pd.DataFrame:
    out = base.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(base.index))

    macro_cols = (
        "fed_funds_rate",
        "usd_eur",
        "usd_jpy",
        "yield_spread_10y2y",
        "breakeven_inflation",
        "vix",
        "cpi_yoy",
        "unrate",
    )

    if macro is not None and not macro.empty:
        m = macro.copy()
        m.index = pd.to_datetime(m.index).normalize()
        m = m.reindex(idx).sort_index().shift(1).ffill()
        for c in macro_cols:
            out[c] = m[c].fillna(0.0) if c in m.columns else 0.0
    else:
        for c in macro_cols:
            out[c] = 0.0

    sent_map = [
        ("score_1d", "sentiment_score_1d"),
        ("score_3d", "sentiment_score_3d"),
        ("volume", "sentiment_volume"),
        ("momentum", "sentiment_momentum"),
    ]

    if sentiment is not None and not sentiment.empty:
        s = sentiment.copy()
        s.index = pd.to_datetime(s.index).normalize()
        s = s.reindex(idx).sort_index().shift(1).ffill()
        for a, b in sent_map:
            out[b] = s[a] if a in s.columns else 0.0
        for b in [x[1] for x in sent_map]:
            out[b] = out[b].fillna(0.0)
    else:
        for _, b in sent_map:
            out[b] = 0.0

    return out


def build_base_feature_frame(
    px: pd.DataFrame,
    macro: pd.DataFrame | None,
    sentiment: pd.DataFrame | None,
) -> pd.DataFrame:
    feats = build_price_features(px)
    attach_seasonality(px.index, feats)
    merged = merge_macro_sentiment_lagged(feats, macro if macro is not None else pd.DataFrame(), sentiment if sentiment is not None else pd.DataFrame())
    merged["regime_label"] = 0.0
    merged["regime_confidence"] = 0.0
    return merged


def attach_regime_columns(df: pd.DataFrame, regime_label: pd.Series, regime_confidence: pd.Series) -> pd.DataFrame:
    out = df.copy()
    rl = regime_label.reindex(out.index)
    rc = regime_confidence.reindex(out.index)
    out["regime_label"] = rl.ffill().fillna(0.0).astype(float)
    out["regime_confidence"] = rc.ffill().fillna(0.0).astype(float)
    return out


def add_targets(df: pd.DataFrame, close: pd.Series) -> pd.DataFrame:
    out = df.copy()
    c = close.reindex(out.index).astype(float)
    out["target_5d"] = ((c.shift(-5) / c - 1.0) > 0.01).astype(int)
    out["target_10d"] = ((c.shift(-10) / c - 1.0) > 0.015).astype(int)
    out["target_21d"] = ((c.shift(-21) / c - 1.0) > 0.02).astype(int)
    return out
