"""Market refresh, feature materialization, and live signal payloads."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COMMODITIES
from app.data.fetcher import ingest_commodity_prices, ingest_macro_indicators, load_macro_dataframe
from app.data.cot_fetcher import get_cot_history
from app.data.loader import load_price_ohlcv, load_sentiment_panel
from app.db.models import EiaInventory
from app.data.sentiment_fetcher import ingest_sentiment
from app.db.models import BacktestResult
from app.db.operations import bulk_insert_signals, load_close_history
from app.ml.correlation_filter import deduplicate_correlated_signals
from app.ml.features import attach_regime_columns, build_base_feature_frame, add_targets
from app.ml.predictor import build_signal_payload
from app.ml.regime import ensure_regime_bundle, fit_and_save_regime, predict_regime_series

logger = logging.getLogger(__name__)

DEFAULT_STATS: dict[str, Any] = {
    "win_rate": 0.55,
    "sharpe_ratio": 1.0,
    "max_drawdown": -0.10,
    "num_trades": 0,
    "avg_win_pct": 0.02,
    "avg_loss_pct": 0.02,
    "total_return": 0.0,
}


async def refresh_external_data(session: AsyncSession) -> dict[str, Any]:
    price_updates = await ingest_commodity_prices(session)
    macro_updates = await ingest_macro_indicators(session)
    headline_count = 0
    try:
        headline_count = await ingest_sentiment(session)
    except Exception:
        headline_count = 0
    return {"prices": price_updates, "macros": macro_updates, "headlines": headline_count}


async def fetch_latest_backtest(session: AsyncSession, ticker: str) -> dict[str, Any]:
    q21 = await session.execute(
        select(BacktestResult)
        .where(BacktestResult.ticker == ticker, BacktestResult.horizon == "21d")
        .order_by(desc(BacktestResult.run_at), desc(BacktestResult.id))
        .limit(1)
    )
    row = q21.scalars().first()
    if row is None:
        q_any = await session.execute(
            select(BacktestResult)
            .where(BacktestResult.ticker == ticker)
            .order_by(desc(BacktestResult.run_at), desc(BacktestResult.id))
            .limit(1)
        )
        row = q_any.scalars().first()
    if row is None:
        logger.warning(
            "No backtest_results for %s; Kelly sizing uses avg_win_pct=0.02 avg_loss_pct=0.02 defaults.",
            ticker,
        )
        return dict(DEFAULT_STATS)

    def to_float(value: Any) -> float:
        return float(value) if value is not None else 0.0

    trades = row.num_trades if row.num_trades is not None else 0
    return {
        "win_rate": to_float(row.win_rate),
        "sharpe_ratio": to_float(row.sharpe_ratio),
        "max_drawdown": to_float(row.max_drawdown),
        "num_trades": int(trades),
        "avg_win_pct": to_float(row.avg_win_pct),
        "avg_loss_pct": to_float(row.avg_loss_pct),
        "total_return": to_float(row.total_return),
    }


def sentiment_from_row(series: pd.Series) -> dict[str, Any]:
    score_1 = float(series.get("sentiment_score_1d", 0) or 0)
    score_3 = float(series.get("sentiment_score_3d", 0) or 0)
    momentum = float(series.get("sentiment_momentum", 0) or 0)
    volume = int(float(series.get("sentiment_volume", 0) or 0))
    if score_1 > 0.05:
        label = "Bullish"
    elif score_1 < -0.05:
        label = "Bearish"
    else:
        label = "Neutral"
    return {"score_1d": score_1, "score_3d": score_3, "momentum": momentum, "volume": volume, "label": label}


def history_to_wide(history_map: dict[str, list[tuple[Any, float]]]) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for ticker, pairs in history_map.items():
        if not pairs:
            continue
        idx = [pd.Timestamp(dt) for dt, _ in pairs]
        vals = [px for _, px in pairs]
        columns[str(ticker)] = pd.Series(vals, index=idx)
    frame = pd.DataFrame(columns)
    return frame.sort_index().ffill()


async def _load_cot_df(session: AsyncSession, ticker: str) -> pd.DataFrame:
    try:
        async with session.begin_nested():
            rows = await get_cot_history(session, ticker, weeks=260)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df.index = pd.to_datetime(df["report_date"])
        return df.drop(columns=["report_date"])
    except Exception as exc:
        logger.debug("COT load failed for %s: %s", ticker, exc)
        return pd.DataFrame()


async def _load_usda_df(session: AsyncSession, ticker: str) -> pd.DataFrame:
    """Load USDA PSD rows for this ticker from the usda_psd table."""
    from sqlalchemy import text as _text
    try:
        async with session.begin_nested():
            result = await session.execute(
                _text("SELECT attribute_id, market_year, value FROM usda_psd WHERE ticker = :ticker ORDER BY market_year"),
                {"ticker": ticker},
            )
            rows = result.fetchall()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows, columns=["attribute_id", "market_year", "value"])
    except Exception as exc:
        logger.debug("USDA load failed for %s: %s", ticker, exc)
        return pd.DataFrame()


async def _load_eia_df(session: AsyncSession, ticker: str) -> pd.DataFrame:
    """Load EIA inventory rows for this ticker (all series_ids) from the DB."""
    from sqlalchemy import desc
    try:
        async with session.begin_nested():
            result = await session.execute(
                select(EiaInventory)
                .where(EiaInventory.ticker == ticker)
                .order_by(EiaInventory.report_date)
            )
            rows = result.scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {"series_id": r.series_id, "report_date": r.report_date, "value": float(r.value) if r.value is not None else None, "wow_change": float(r.wow_change) if r.wow_change is not None else None}
            for r in rows
        ])
    except Exception as exc:
        logger.debug("EIA load failed for %s: %s", ticker, exc)
        return pd.DataFrame()


async def _load_cross_asset_df(session: AsyncSession, exclude_ticker: str) -> pd.DataFrame:
    """Load close prices of select reference tickers as cross-asset features."""
    ref_tickers = ["CL=F", "GC=F", "HG=F", "ZC=F"]
    refs = [t for t in ref_tickers if t != exclude_ticker]
    hist = await load_close_history(session, refs, lookback_days=1200)
    cols = {}
    for t, pairs in hist.items():
        if pairs:
            idx = [pd.Timestamp(dt) for dt, _ in pairs]
            cols[t.replace("=F", "").replace("=", "")] = pd.Series([px for _, px in pairs], index=idx)
    return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()


async def materialize_training_frame(session: AsyncSession, ticker: str) -> pd.DataFrame | None:
    macro = await load_macro_dataframe(session)
    px = await load_price_ohlcv(session, ticker)
    if px.empty:
        return None
    sent = await load_sentiment_panel(session, ticker)
    cot = await _load_cot_df(session, ticker)
    cross = await _load_cross_asset_df(session, ticker)
    usda = await _load_usda_df(session, ticker)
    eia = await _load_eia_df(session, ticker)
    base = build_base_feature_frame(px, macro, sent, cot=cot, cross_asset=cross, usda=usda, eia=eia)
    bundle = ensure_regime_bundle(ticker)
    if bundle is None:
        try:
            await asyncio.to_thread(fit_and_save_regime, ticker, base)
        except Exception as exc:
            logger.warning("Regime fit skipped for %s: %s", ticker, exc)
        bundle = ensure_regime_bundle(ticker)
    reg_label, reg_conf = await asyncio.to_thread(predict_regime_series, base, bundle)
    merged = attach_regime_columns(base, reg_label, reg_conf)
    labeled = add_targets(merged, px["close"])
    return labeled


async def compute_signal_payloads(session: AsyncSession) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    macro = await load_macro_dataframe(session)
    raw: list[dict[str, Any]] = []
    for ticker in COMMODITIES:
        px = await load_price_ohlcv(session, ticker)
        if px.empty:
            continue
        sent = await load_sentiment_panel(session, ticker)
        cot = await _load_cot_df(session, ticker)
        cross = await _load_cross_asset_df(session, ticker)
        usda = await _load_usda_df(session, ticker)
        eia = await _load_eia_df(session, ticker)
        base = build_base_feature_frame(px, macro, sent, cot=cot, cross_asset=cross, usda=usda, eia=eia)
        bundle = ensure_regime_bundle(ticker)
        if bundle is None:
            try:
                await asyncio.to_thread(fit_and_save_regime, ticker, base)
            except Exception as exc:
                logger.warning("Regime fit skipped for %s: %s", ticker, exc)
            bundle = ensure_regime_bundle(ticker)
        reg_label, reg_conf = await asyncio.to_thread(predict_regime_series, base, bundle)
        merged = attach_regime_columns(base, reg_label, reg_conf)
        usable = merged.dropna(how="any")
        if usable.empty:
            continue
        tail = usable.iloc[-1]
        last_px = float(px["close"].iloc[-1])
        stats_block = await fetch_latest_backtest(session, ticker)
        sent_block = sentiment_from_row(tail)
        regime_l = float(tail.get("regime_label", 0))
        regime_c = float(tail.get("regime_confidence", 0))
        payload = await asyncio.to_thread(
            build_signal_payload,
            ticker,
            usable,
            tail,
            regime_l,
            regime_c,
            last_px,
            sent_block,
            stats_block,
        )
        raw.append(payload)
    hist = await load_close_history(session, list(COMMODITIES.keys()), 120)
    wide = history_to_wide(hist)
    try:
        filtered = await asyncio.to_thread(deduplicate_correlated_signals, raw, wide)
    except Exception as exc:
        logger.warning("Correlation filter skipped: %s", exc)
        filtered = raw
    return filtered, raw


async def gather_training_frames(session: AsyncSession) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for ticker in COMMODITIES:
        frame = await materialize_training_frame(session, ticker)
        if frame is not None:
            out[ticker] = frame
    return out


def payloads_to_signal_rows(filtered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in filtered:
        rows.append(
            {
                "ticker": str(p["ticker"]),
                "signal": str(p["signal"]),
                "avg_confidence": p.get("avg_confidence"),
                "confidence_5d": p.get("confidence_5d"),
                "confidence_10d": p.get("confidence_10d"),
                "confidence_21d": p.get("confidence_21d"),
                "regime": int(p["regime"]) if p.get("regime") is not None else None,
                "position_size_pct": p.get("position_size_pct"),
                "shap_json": p.get("shap_features") or [],
                "sentiment_json": p.get("sentiment") or {},
                "correlation_filtered": bool(p.get("correlation_filtered", False)),
            }
        )
    return rows


async def run_signal_refresh(session: AsyncSession) -> dict[str, Any]:
    from app.services.risk_service import apply_portfolio_limits, portfolio_summary

    ingestion = await refresh_external_data(session)
    filtered, raw_list = await compute_signal_payloads(session)
    if not filtered:
        filtered = placeholder_payloads()
        raw_list = list(filtered)

    # Apply portfolio-level exposure limits and correlation-aware sizing
    close_hist = await load_close_history(session, list(COMMODITIES.keys()), 120)
    close_price_dict: dict[str, pd.DataFrame] = {}
    for t, pairs in close_hist.items():
        if pairs:
            close_price_dict[t] = pd.DataFrame({"close": [px for _, px in pairs]})
    filtered = await asyncio.to_thread(apply_portfolio_limits, filtered, close_price_dict)
    risk_data = portfolio_summary(filtered)

    rows = payloads_to_signal_rows(filtered)
    await bulk_insert_signals(session, rows)
    await session.commit()
    refreshed_at = datetime.now(tz=UTC).isoformat()
    return {
        "ingestion": ingestion,
        "filtered": filtered,
        "raw": raw_list,
        "refreshed_at": refreshed_at,
        "filtered_count": len(filtered),
        "risk": risk_data,
    }


def placeholder_payloads() -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    stamp = datetime.now(tz=UTC).isoformat()
    for ticker, label in COMMODITIES.items():
        payloads.append(
            {
                "ticker": ticker,
                "name": label,
                "signal": "HOLD",
                "avg_confidence": 0.0,
                "confidence_5d": 0.0,
                "confidence_10d": 0.0,
                "confidence_21d": 0.0,
                "current_price": 0.0,
                "regime": 0,
                "regime_label": "Unknown",
                "regime_confidence": 0.0,
                "consensus": False,
                "position_size_pct": 0.0,
                "suggested_action": "No price history yet.",
                "sentiment": {"score_1d": 0.0, "score_3d": 0.0, "momentum": 0.0, "volume": 0, "label": "Neutral"},
                "backtest": {
                    "win_rate": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "num_trades": 0,
                    "total_return": 0.0,
                    "avg_win_pct": 0.02,
                    "avg_loss_pct": 0.02,
                },
                "shap_features": [],
                "generated_at": stamp,
                "correlation_filtered": False,
            }
        )
    return payloads