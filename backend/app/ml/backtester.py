"""Signal backtests via vectorbt."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


def _trade_return_array(pf: vbt.Portfolio) -> np.ndarray:
    """Extract per-trade returns as a 1-D float array (vectorbt MappedArray-safe)."""
    rets = pf.trades.returns
    if hasattr(rets, "values"):
        arr = np.asarray(rets.values, dtype=float).ravel()
    else:
        arr = np.asarray(rets, dtype=float).ravel()
    return arr[np.isfinite(arr)]


def _finite_scalar(value: float | None, default: float = 0.0) -> float:
    if value is None:
        return default
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v


def run_signal_backtest(price: pd.Series, entries: pd.Series) -> dict[str, Any]:
    px = price.astype(float)
    px = px.reindex(pd.DatetimeIndex(px.index).sort_values()).ffill()
    sig = entries.reindex(px.index).fillna(0).astype(int)
    ent = sig.eq(1)
    exits = sig.shift(21).fillna(0).astype(int).eq(1)
    pf = vbt.Portfolio.from_signals(px, entries=ent, exits=exits, init_cash=100000.0, freq="d")
    rets_arr = _trade_return_array(pf)
    rets_pos = rets_arr[rets_arr > 0]
    rets_neg = rets_arr[rets_arr < 0]
    avg_win = float(rets_pos.mean()) if len(rets_pos) else 0.0
    avg_loss = float(abs(rets_neg.mean())) if len(rets_neg) else 0.0
    sharpe_scalar = _finite_scalar(pf.sharpe_ratio())
    mdd_scalar = _finite_scalar(pf.max_drawdown())
    trades_records = getattr(pf.trades, "records", None)
    if trades_records is None:
        trades_count = 0
    else:
        trades_count = int(len(trades_records))
    win_rate = 0.0
    if trades_count:
        win_rate = _finite_scalar(pf.trades.win_rate())
    total_ret_scalar = _finite_scalar(pf.total_return())
    return {
        "total_return": round(total_ret_scalar, 4),
        "sharpe_ratio": round(sharpe_scalar, 4),
        "max_drawdown": round(mdd_scalar, 4),
        "win_rate": round(win_rate, 4),
        "avg_win_pct": round(_finite_scalar(avg_win), 4),
        "avg_loss_pct": round(_finite_scalar(avg_loss), 4),
        "num_trades": trades_count,
    }
