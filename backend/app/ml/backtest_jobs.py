"""Rebuild `backtest_results` from stored OOS probabilities + vectorbt (one row per ticker × horizon).

Called after training or on schedule; aligns entry signals using the same horizon thresholds as live predictor.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COMMODITIES, HORIZONS
from app.data.loader import load_price_ohlcv
from app.db.models import OosPrediction
from app.db.operations import delete_backtests_for_tickers, insert_backtests
from app.ml.backtester import run_signal_backtest
from app.ml.consensus_thresh import HORIZON_PROB_THRESHOLDS

logger = logging.getLogger(__name__)


async def _oos_prob_series(session: AsyncSession, ticker: str, horizon: str) -> pd.Series | None:
    q = await session.execute(
        select(OosPrediction.date, OosPrediction.y_prob)
        .where(OosPrediction.ticker == ticker, OosPrediction.horizon == horizon)
        .order_by(OosPrediction.date)
    )
    pairs = [(r[0], float(r[1])) for r in q.all()]
    if not pairs:
        return None
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in pairs])
    probs = pd.Series([p for _, p in pairs], index=idx, dtype=float).sort_index()
    return probs


async def rebuild_backtests_after_training(
    session: AsyncSession,
    tickers_scope: Sequence[str] | None = None,
) -> int:
    """If `tickers_scope` is set (e.g. keys from latest train), delete and rebuild only those; else full universe."""
    tickers_loop = list(tickers_scope) if tickers_scope is not None else list(COMMODITIES.keys())
    await delete_backtests_for_tickers(session, tickers_loop)

    rows_out: list[dict[str, Any]] = []
    run_at = datetime.now(tz=UTC)

    for ticker in tickers_loop:
        px_df = await load_price_ohlcv(session, ticker)
        if px_df.empty:
            continue
        price = px_df["close"].astype(float)
        price.index = pd.DatetimeIndex(pd.to_datetime(price.index))

        for horizon in HORIZONS:
            probs_idx = await _oos_prob_series(session, ticker, horizon)
            thresh = float(HORIZON_PROB_THRESHOLDS[horizon])
            if probs_idx is None or probs_idx.empty:
                continue

            probs_idx.index = pd.DatetimeIndex(pd.to_datetime(probs_idx.index))

            aligned = probs_idx.reindex(price.index).ffill().fillna(0.0)
            entries = (aligned.astype(float) >= thresh).astype(int)

            stats = await asyncio.to_thread(run_signal_backtest, price, entries)

            rows_out.append(
                {
                    "ticker": ticker,
                    "horizon": horizon,
                    "run_at": run_at,
                    "total_return": stats["total_return"],
                    "sharpe_ratio": stats["sharpe_ratio"],
                    "max_drawdown": stats["max_drawdown"],
                    "win_rate": stats["win_rate"],
                    "avg_win_pct": stats["avg_win_pct"],
                    "avg_loss_pct": stats["avg_loss_pct"],
                    "num_trades": stats["num_trades"],
                }
            )

    if rows_out:
        await insert_backtests(session, rows_out)
        await session.commit()

    logger.info("Backtest persistence: inserted %s rows.", len(rows_out))
    return len(rows_out)
