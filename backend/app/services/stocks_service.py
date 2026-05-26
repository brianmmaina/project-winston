"""High-level orchestration for the stock side of the advisor:

- ``refresh_stocks_data``: ingest universe metadata + price history.
- ``build_panel_features``: fetch stock_prices + SPY + sector map from Postgres,
  produce the feature panel used by the ranker.
- ``train_stocks_panel``: walk-forward training + persistence of OOS predictions
  and per-fold metrics.
- ``run_daily_ranking``: score the latest panel, apply top-K & sector caps, and
  persist the ranking to ``portfolio_rankings`` ready for the UI to consume.

Mirrors ``signals_service`` for commodities so the API layer and scheduler can
call each side with parallel verbs.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants_stocks import (
    BENCHMARK_TICKER,
    STOCK_SECTORS,
    STOCKS,
)
from app.data.loader import (
    load_benchmark_series,
    load_stock_metadata,
    load_stock_oos_scores,
    load_stock_panel,
    load_stock_sentiment_panel,
)
from app.data.stock_sentiment import ingest_stock_sentiment
from app.data.stocks_fetcher import ingest_stock_prices, seed_instrument_metadata
from app.db.operations import (
    insert_backtests,
    insert_model_runs,
    insert_oos_predictions,
    upsert_portfolio_equity,
    upsert_portfolio_holdings,
    upsert_portfolio_rankings,
)
from app.ml.features_stocks import build_stock_panel_features
from app.ml.portfolio_backtest import (
    BacktestConfig,
    backtest_topk_portfolio,
    equity_to_persistence_rows,
    holdings_to_persistence_rows,
)
from app.ml.stocks_ranker import (
    fold_metrics_to_model_runs,
    load_stocks_bundle,
    rank_and_apply_sector_caps,
    score_latest,
    train_walk_forward,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 5
DEFAULT_TOP_K = 25
DEFAULT_MAX_PER_SECTOR = 5
PANEL_LOOKBACK_DAYS = 5 * 365 + 90


async def refresh_stocks_data(session: AsyncSession) -> dict[str, Any]:
    """Seed metadata + pull OHLCV + score today's news sentiment.

    Mirrors ``refresh_external_data`` for commodities. The sentiment step is
    best-effort: a network/feed failure must not fail the whole refresh.
    """
    meta_count = await seed_instrument_metadata(session)
    stats = await ingest_stock_prices(session)

    sentiment_stats: dict[str, Any] = {"ran": False}
    try:
        sentiment_stats = await ingest_stock_sentiment(session)
        sentiment_stats["ran"] = True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("stock sentiment ingest failed (non-fatal): %s", exc)

    return {
        "metadata_seeded": meta_count,
        "sentiment": sentiment_stats,
        **stats,
    }


async def _sector_map_from_db_or_constants(session: AsyncSession) -> dict[str, str]:
    """Prefer DB-seeded metadata, fall back to constants module if metadata empty."""
    meta_df = await load_stock_metadata(session)
    if not meta_df.empty:
        return {
            str(row.ticker): (row.sector or "Unknown")
            for row in meta_df.itertuples(index=False)
        }
    return dict(STOCK_SECTORS)


async def build_panel_features(
    session: AsyncSession,
    *,
    lookback_days: int = PANEL_LOOKBACK_DAYS,
    target_horizons: tuple[int, ...] = (5, 21),
) -> pd.DataFrame:
    end_d = date.today()
    start_d = end_d - timedelta(days=lookback_days)
    panel = await load_stock_panel(
        session, tickers=list(STOCKS.keys()), start=start_d, end=end_d
    )
    if panel.empty:
        LOGGER.warning("stock_prices is empty for window %s..%s", start_d, end_d)
        return pd.DataFrame()
    benchmark = await load_benchmark_series(session, BENCHMARK_TICKER)
    sector_map = await _sector_map_from_db_or_constants(session)
    sentiment = await load_stock_sentiment_panel(
        session, tickers=list(STOCKS.keys()), start=start_d, end=end_d
    )
    return await asyncio.to_thread(
        build_stock_panel_features,
        panel,
        benchmark,
        sector_map,
        horizons=target_horizons,
        sentiment=sentiment if not sentiment.empty else None,
    )


async def train_stocks_panel(
    session: AsyncSession,
    *,
    target_horizon: int = DEFAULT_HORIZON_DAYS,
) -> dict[str, Any]:
    panel_feats = await build_panel_features(session, target_horizons=(target_horizon,))
    if panel_feats.empty:
        return {"folds": 0, "oos_rows": 0, "trained": False}

    fold_metrics, oos_rows, _, _ = await asyncio.to_thread(
        train_walk_forward, panel_feats, target_horizon
    )
    if oos_rows:
        await insert_oos_predictions(session, oos_rows)
    runs = fold_metrics_to_model_runs(fold_metrics, f"{target_horizon}d")
    if runs:
        await insert_model_runs(session, runs)
    await session.commit()

    return {
        "folds": len(fold_metrics),
        "oos_rows": len(oos_rows),
        "trained": bool(fold_metrics),
        "ic_mean": float(sum(m.ic for m in fold_metrics) / max(1, len(fold_metrics))),
        "rank_ic_mean": float(
            sum(m.rank_ic for m in fold_metrics) / max(1, len(fold_metrics))
        ),
        "horizon": f"{target_horizon}d",
    }


async def run_daily_ranking(
    session: AsyncSession,
    *,
    target_horizon: int = DEFAULT_HORIZON_DAYS,
    top_k: int = DEFAULT_TOP_K,
    max_per_sector: int | None = DEFAULT_MAX_PER_SECTOR,
) -> dict[str, Any]:
    """Score today's panel and persist ``portfolio_rankings`` rows.

    Returns ``{date, count, in_topk, ranker_loaded, horizon}``. If no model
    artifact exists yet (Phase 3 not run), ``ranker_loaded`` is ``False`` and
    nothing is persisted.
    """
    panel_feats = await build_panel_features(session, target_horizons=(target_horizon,))
    if panel_feats.empty:
        return {
            "date": None,
            "count": 0,
            "in_topk": 0,
            "ranker_loaded": False,
            "horizon": f"{target_horizon}d",
        }

    bundle = await asyncio.to_thread(load_stocks_bundle, f"{target_horizon}d")
    if bundle is None:
        return {
            "date": None,
            "count": 0,
            "in_topk": 0,
            "ranker_loaded": False,
            "horizon": f"{target_horizon}d",
        }

    scored = await asyncio.to_thread(score_latest, panel_feats, bundle)
    if scored.empty:
        return {
            "date": None,
            "count": 0,
            "in_topk": 0,
            "ranker_loaded": True,
            "horizon": f"{target_horizon}d",
        }

    ranked = await asyncio.to_thread(
        rank_and_apply_sector_caps,
        scored,
        top_k=top_k,
        max_per_sector=max_per_sector,
    )

    rank_date = pd.Timestamp(ranked["date"].iloc[0]).date()
    generated_at = datetime.now(tz=UTC)
    rows: list[dict[str, Any]] = []
    for _, r in ranked.iterrows():
        rows.append(
            {
                "date": rank_date,
                "ticker": str(r["ticker"]),
                "score": float(r["score"]),
                "rank": int(r["rank"]),
                "sector": str(r.get("sector") or "Unknown"),
                "in_topk": bool(r["in_topk"]),
                "horizon": f"{target_horizon}d",
                "generated_at": generated_at,
            }
        )
    if rows:
        await upsert_portfolio_rankings(session, rows)
        await session.commit()

    return {
        "date": rank_date.isoformat(),
        "count": len(rows),
        "in_topk": int(ranked["in_topk"].sum()),
        "ranker_loaded": True,
        "horizon": f"{target_horizon}d",
    }


async def run_portfolio_backtest(
    session: AsyncSession,
    *,
    target_horizon: int = DEFAULT_HORIZON_DAYS,
    top_k: int = DEFAULT_TOP_K,
    max_per_sector: int | None = DEFAULT_MAX_PER_SECTOR,
    rebalance_days: int = 5,
    transaction_cost_bps: float = 5.0,
) -> dict[str, Any]:
    """End-to-end portfolio backtest:
    1. Pull stock-side OOS scores from ``oos_predictions``.
    2. Pull historical OHLCV + SPY benchmark.
    3. Run ``backtest_topk_portfolio`` with the requested config.
    4. Persist equity curve, holdings, and a ``backtest_results`` summary row.
    """
    horizon_str = f"{target_horizon}d"
    score_panel = await load_stock_oos_scores(session, horizon=horizon_str)
    if score_panel.empty:
        return {"ran": False, "reason": "no_oos_scores", "horizon": horizon_str}

    start_d = pd.to_datetime(score_panel["date"].min()).date()
    end_d = pd.to_datetime(score_panel["date"].max()).date()

    price_panel_long = await load_stock_panel(session, tickers=None, start=start_d, end=end_d)
    if price_panel_long.empty:
        return {"ran": False, "reason": "no_prices", "horizon": horizon_str}

    sector_map = await _sector_map_from_db_or_constants(session)
    benchmark = await load_benchmark_series(session, BENCHMARK_TICKER)

    cfg = BacktestConfig(
        top_k=top_k,
        max_per_sector=max_per_sector,
        rebalance_days=rebalance_days,
        transaction_cost_bps=transaction_cost_bps,
    )
    result = await asyncio.to_thread(
        backtest_topk_portfolio,
        score_panel,
        price_panel_long[["date", "ticker", "close"]],
        sector_map,
        benchmark,
        cfg,
    )

    if result.get("empty"):
        return {"ran": False, "reason": result.get("reason", "empty"), "horizon": horizon_str}

    eq: pd.Series = result["equity_curve"]
    bench_curve: pd.Series = result["benchmark_curve"]
    daily_ret: pd.Series = result["daily_returns"]
    holdings: pd.DataFrame = result["holdings"]
    metrics: dict[str, Any] = result["metrics"]

    equity_rows = equity_to_persistence_rows(eq, bench_curve, daily_ret)
    holdings_rows = holdings_to_persistence_rows(holdings)
    if equity_rows:
        await upsert_portfolio_equity(session, equity_rows)
    if holdings_rows:
        await upsert_portfolio_holdings(session, holdings_rows)

    bt_summary = {
        "ticker": "PANEL",
        "horizon": horizon_str,
        "asset_class": "stock",
        "run_at": datetime.now(tz=UTC),
        "total_return": float(metrics["total_return"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "win_rate": float(metrics["win_rate"]),
        # ``avg_win_pct`` / ``avg_loss_pct`` are repurposed for stock portfolio:
        # benchmark return and information-ratio vs benchmark, respectively.
        "avg_win_pct": float(metrics.get("benchmark_total_return") or 0.0),
        "avg_loss_pct": float(metrics["info_ratio_vs_benchmark"]),
        "num_trades": int(metrics["num_rebalances"]),
    }
    await insert_backtests(session, [bt_summary])
    await session.commit()

    return {
        "ran": True,
        "horizon": horizon_str,
        "metrics": metrics,
        "equity_rows": len(equity_rows),
        "holdings_rows": len(holdings_rows),
    }


async def get_active_tickers(session: AsyncSession) -> list[str]:
    """Return list of active stock tickers from instrument_metadata."""
    from sqlalchemy import select
    from app.db.models import InstrumentMetadata
    q = await session.execute(
        select(InstrumentMetadata.ticker)
        .where(InstrumentMetadata.asset_class == "stock", InstrumentMetadata.is_active.is_(True))
        .order_by(InstrumentMetadata.ticker)
    )
    return [row[0] for row in q.all()]
