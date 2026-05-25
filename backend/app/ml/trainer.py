"""Async wrappers for commodity model training."""

from __future__ import annotations

import asyncio

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import HORIZONS
from app.db.models import ModelHyperparam
from app.db.operations import insert_model_runs, replace_oos_predictions
from app.ml.backtest_jobs import rebuild_backtests_after_training
from app.ml.trainer_support import train_one_horizon_sync
from app.ml.tuner import default_lgb_params, default_xgb_params


async def load_best_params(session: AsyncSession | None, ticker: str, horizon: str):
    xp = dict(default_xgb_params())
    lp = dict(default_lgb_params())
    if session is None:
        return xp, lp
    qx = await session.execute(
        select(ModelHyperparam).where(
            ModelHyperparam.ticker == ticker,
            ModelHyperparam.horizon == horizon,
            ModelHyperparam.model_type == "xgb",
        ).order_by(ModelHyperparam.id.desc()).limit(1)
    )
    rx = qx.scalars().first()
    if rx is not None:
        xp.update(dict(rx.params_json))
    ql = await session.execute(
        select(ModelHyperparam).where(
            ModelHyperparam.ticker == ticker,
            ModelHyperparam.horizon == horizon,
            ModelHyperparam.model_type == "lgbm",
        ).order_by(ModelHyperparam.id.desc()).limit(1)
    )
    rl = ql.scalars().first()
    if rl is not None:
        lp.update(dict(rl.params_json))
    return xp, lp


async def train_ticker_horizons(session: AsyncSession, ticker: str, frame: pd.DataFrame) -> None:
    for horizon in HORIZONS:
        xgb_p, lgb_p = await load_best_params(session, ticker, horizon)
        oos, runs, _ = await asyncio.to_thread(train_one_horizon_sync, ticker, horizon, frame, xgb_p, lgb_p)
        await replace_oos_predictions(session, ticker, horizon, oos)
        if runs:
            await insert_model_runs(session, runs)
    await session.commit()


async def train_all_tickers(session: AsyncSession, frames: dict[str, pd.DataFrame]) -> None:
    for ticker, frame in frames.items():
        await train_ticker_horizons(session, ticker, frame)
    await rebuild_backtests_after_training(session, tuple(frames.keys()))
