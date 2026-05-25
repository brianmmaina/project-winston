"""Top-K portfolio backtest for the stock ranker.

Takes (a) the cross-sectional score panel (OOS predictions from walk-forward
training, plus optionally newer live scores) and (b) the OHLCV panel, and walks
through time:

  * On rebalance days, take the top-K names by score with per-sector caps,
    equal-weight (default) or score-proportional. Compute the dollar turnover
    against the previous portfolio.
  * Between rebalance days, hold positions; daily P&L is the weighted average
    of constituent daily returns.
  * Apply linear transaction cost (basis points × turnover dollars).
  * Track equity, daily returns, drawdown, turnover.

Returns:
- equity_curve, benchmark_curve, daily_returns: pd.Series date-indexed
- holdings: pd.DataFrame [date, ticker, weight, sector] for every rebalance day
- metrics dict: total_return, sharpe, max_drawdown, win_rate, num_trades,
  annual_turnover, info_ratio_vs_benchmark, benchmark_total_return
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class BacktestConfig:
    top_k: int = 25
    max_per_sector: int | None = 5
    rebalance_days: int = 5
    transaction_cost_bps: float = 5.0
    initial_equity: float = 100_000.0
    weight_scheme: str = "equal"  # or "score_softmax"


def _pivot_panel(panel: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Long-form (date, ticker, value) → wide-form (date × ticker) matrix."""
    p = panel[["date", "ticker", value_col]].copy()
    p["date"] = pd.to_datetime(p["date"])
    return p.pivot(index="date", columns="ticker", values=value_col).sort_index()


def _select_top_k(
    scores_row: pd.Series,
    sector_map: dict[str, str],
    top_k: int,
    max_per_sector: int | None,
) -> list[str]:
    cleaned = scores_row.dropna()
    if cleaned.empty:
        return []
    ordered = cleaned.sort_values(ascending=False)
    selected: list[str] = []
    per_sector: dict[str, int] = {}
    for ticker in ordered.index:
        if len(selected) >= top_k:
            break
        sec = sector_map.get(str(ticker), "Unknown")
        if max_per_sector is not None and per_sector.get(sec, 0) >= max_per_sector:
            continue
        selected.append(str(ticker))
        per_sector[sec] = per_sector.get(sec, 0) + 1
    return selected


def _weights_for(
    selected: list[str],
    scores_row: pd.Series,
    scheme: str,
) -> dict[str, float]:
    if not selected:
        return {}
    if scheme == "score_softmax":
        s = scores_row.reindex(selected).astype(float)
        s = s - s.max()
        w = np.exp(s.values)
        w = w / w.sum()
        return {t: float(v) for t, v in zip(selected, w)}
    # equal-weight default
    eq = 1.0 / float(len(selected))
    return {t: eq for t in selected}


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    dd = (equity / running_max - 1.0).min()
    if dd != dd:
        return 0.0
    return float(dd)


def _sharpe(returns: pd.Series) -> float:
    cleaned = returns.dropna()
    if cleaned.empty or cleaned.std() == 0:
        return 0.0
    return float(np.sqrt(TRADING_DAYS_PER_YEAR) * cleaned.mean() / cleaned.std())


def _info_ratio(strategy: pd.Series, benchmark: pd.Series) -> float:
    a, b = strategy.align(benchmark, join="inner")
    excess = a - b
    cleaned = excess.dropna()
    if cleaned.empty or cleaned.std() == 0:
        return 0.0
    return float(np.sqrt(TRADING_DAYS_PER_YEAR) * cleaned.mean() / cleaned.std())


def backtest_topk_portfolio(
    score_panel: pd.DataFrame,
    price_panel: pd.DataFrame,
    sector_map: dict[str, str],
    benchmark: pd.Series | None = None,
    config: BacktestConfig | None = None,
) -> dict[str, object]:
    """Run the top-K portfolio backtest.

    Args:
        score_panel: long-form ``[date, ticker, score]`` (typically OOS
            predictions from ``train_walk_forward``).
        price_panel: long-form ``[date, ticker, close]`` for the full universe.
        sector_map: ticker → sector.
        benchmark: optional date-indexed close series (e.g. SPY).
        config: ``BacktestConfig`` override; defaults applied otherwise.
    """
    cfg = config or BacktestConfig()
    if score_panel is None or score_panel.empty:
        return {"empty": True}
    if price_panel is None or price_panel.empty:
        return {"empty": True}

    score_wide = _pivot_panel(score_panel.rename(columns={"score": "score"}), "score")
    price_wide = _pivot_panel(price_panel.rename(columns={"close": "close"}), "close")

    # Restrict to dates present in both
    common = score_wide.index.intersection(price_wide.index)
    score_wide = score_wide.loc[common]
    price_wide = price_wide.loc[common]
    if len(common) < 10:
        return {"empty": True, "reason": "insufficient_overlap", "common_dates": len(common)}

    daily_ret_wide = price_wide.pct_change().fillna(0.0)

    weights: dict[str, float] = {}
    holdings_records: list[dict[str, object]] = []
    equity_records: list[tuple[pd.Timestamp, float, float]] = []
    daily_return_records: list[tuple[pd.Timestamp, float]] = []
    turnover_records: list[tuple[pd.Timestamp, float]] = []

    equity = cfg.initial_equity
    bench_equity_init: float | None = None
    last_rebalance_idx = -10**9  # force rebalance on first qualifying day
    rebalance_count = 0
    realised_returns: list[float] = []

    for i, day in enumerate(common):
        # Mark-to-market the existing book
        if weights:
            scaled_ret = sum(
                w * float(daily_ret_wide.loc[day, t]) for t, w in weights.items()
                if t in daily_ret_wide.columns
            )
        else:
            scaled_ret = 0.0
        equity *= (1.0 + scaled_ret)
        daily_return_records.append((day, scaled_ret))
        realised_returns.append(scaled_ret)

        if benchmark is not None:
            bench_today = float(benchmark.reindex([day]).iloc[0]) if day in benchmark.index else float("nan")
            if bench_equity_init is None and bench_today == bench_today:
                bench_equity_init = bench_today
            bench_eq = (
                cfg.initial_equity * (bench_today / bench_equity_init)
                if bench_equity_init is not None and bench_today == bench_today
                else float("nan")
            )
        else:
            bench_eq = float("nan")
        equity_records.append((day, float(equity), float(bench_eq)))

        # Rebalance?
        if (i - last_rebalance_idx) < cfg.rebalance_days:
            continue
        scores_row = score_wide.loc[day]
        if scores_row.dropna().empty:
            continue
        selected = _select_top_k(scores_row, sector_map, cfg.top_k, cfg.max_per_sector)
        new_weights = _weights_for(selected, scores_row, cfg.weight_scheme)

        # Turnover = sum |new - old| over the union of names
        union = set(new_weights) | set(weights)
        turnover_frac = sum(
            abs(new_weights.get(t, 0.0) - weights.get(t, 0.0)) for t in union
        )
        turnover_dollars = float(equity * turnover_frac)
        cost = turnover_dollars * (cfg.transaction_cost_bps / 10_000.0)
        equity -= cost
        turnover_records.append((day, turnover_frac))

        for t, w in new_weights.items():
            holdings_records.append(
                {
                    "date": day.date(),
                    "ticker": t,
                    "weight": w,
                    "sector": sector_map.get(t, "Unknown"),
                    "last_price": float(price_wide.loc[day, t])
                    if t in price_wide.columns
                    else float("nan"),
                }
            )
        weights = new_weights
        last_rebalance_idx = i
        rebalance_count += 1

    if not equity_records:
        return {"empty": True, "reason": "no_equity_records"}

    eq_df = pd.DataFrame(equity_records, columns=["date", "equity", "benchmark_equity"]).set_index("date")
    daily_ret = pd.Series(
        [v for _, v in daily_return_records], index=[d for d, _ in daily_return_records], name="ret"
    )
    holdings = pd.DataFrame(holdings_records)

    bench_daily_ret = (
        eq_df["benchmark_equity"].pct_change().dropna()
        if eq_df["benchmark_equity"].notna().any()
        else pd.Series(dtype=float)
    )

    metrics = {
        "total_return": float(eq_df["equity"].iloc[-1] / cfg.initial_equity - 1.0),
        "sharpe_ratio": _sharpe(daily_ret),
        "max_drawdown": _max_drawdown(eq_df["equity"]),
        "win_rate": float(((daily_ret > 0).sum()) / max(1, (daily_ret != 0).sum())),
        "num_rebalances": int(rebalance_count),
        "annual_turnover": float(
            (sum(v for _, v in turnover_records) * TRADING_DAYS_PER_YEAR)
            / max(1, len(common))
        ),
        "benchmark_total_return": (
            float(eq_df["benchmark_equity"].iloc[-1] / cfg.initial_equity - 1.0)
            if eq_df["benchmark_equity"].notna().any()
            else None
        ),
        "info_ratio_vs_benchmark": _info_ratio(daily_ret, bench_daily_ret),
    }

    return {
        "equity_curve": eq_df["equity"],
        "benchmark_curve": eq_df["benchmark_equity"],
        "daily_returns": daily_ret,
        "holdings": holdings,
        "metrics": metrics,
        "config": cfg,
    }


def equity_to_persistence_rows(
    eq: pd.Series,
    bench: pd.Series,
    daily_ret: pd.Series,
    turnover: Iterable[tuple[pd.Timestamp, float]] | None = None,
) -> list[dict[str, object]]:
    """Adapter for ``portfolio_equity`` upsert."""
    rows: list[dict[str, object]] = []
    t_map = dict(turnover or [])
    for day, equity in eq.items():
        rows.append(
            {
                "date": pd.Timestamp(day).date(),
                "equity": float(equity),
                "benchmark_equity": float(bench.get(day)) if bench is not None and day in bench.index else None,
                "daily_return": float(daily_ret.get(day, 0.0)),
                "turnover": float(t_map.get(day, 0.0)),
            }
        )
    return rows


def holdings_to_persistence_rows(holdings: pd.DataFrame) -> list[dict[str, object]]:
    if holdings is None or holdings.empty:
        return []
    out: list[dict[str, object]] = []
    for _, r in holdings.iterrows():
        out.append(
            {
                "date": r["date"],
                "ticker": str(r["ticker"]),
                "weight": float(r["weight"]),
                "entry_price": float(r["last_price"]) if pd.notna(r["last_price"]) else None,
                "last_price": float(r["last_price"]) if pd.notna(r["last_price"]) else None,
                "sector": str(r.get("sector") or "Unknown"),
            }
        )
    return out
