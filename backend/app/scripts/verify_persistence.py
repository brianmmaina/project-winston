#!/usr/bin/env python3
"""CLI: print model_hyperparams / backtest_results counts (by ticker) and latest timestamps."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db.models import BacktestResult, ModelHyperparam
from app.db.session import async_session_factory


async def _run_async() -> None:
    async with async_session_factory() as session:
        hp_tickers = await session.execute(
            select(ModelHyperparam.ticker, func.count()).group_by(ModelHyperparam.ticker),
        )
        print("model_hyperparams by ticker:")
        for tkr, ct in hp_tickers.all():
            print(f"  {tkr}: {ct}")

        max_tuned = await session.scalar(select(func.max(ModelHyperparam.tuned_at)))
        print("\nLatest model_hyperparams.tuned_at:", max_tuned)

        bt_tickers = await session.execute(select(BacktestResult.ticker, func.count()).group_by(BacktestResult.ticker))
        print("\nbacktest_results by ticker:")
        for tkr, ct in bt_tickers.all():
            print(f"  {tkr}: {ct}")

        max_run = await session.scalar(select(func.max(BacktestResult.run_at)))
        print("\nLatest backtest_results.run_at:", max_run)


def main() -> None:
    asyncio.run(_run_async())


if __name__ == "__main__":
    main()
