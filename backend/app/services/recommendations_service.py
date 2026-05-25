"""Outcome tracking — save agent picks and check prices at 2/4/8 weeks vs SPY."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRecommendation

logger = logging.getLogger(__name__)

_TRACK_RECS = {"STRONG_BUY", "BUY"}


async def save_recommendations(
    run_id: str,
    verified_trades: list[dict[str, Any]],
    session: AsyncSession,
) -> int:
    import yfinance as yf

    actionable = [t for t in verified_trades if t.get("final_recommendation") in _TRACK_RECS]
    if not actionable:
        return 0

    def _prices(tickers: list[str]) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for tk in tickers:
            try:
                out[tk] = yf.Ticker(tk).fast_info.last_price
            except Exception:
                out[tk] = None
        return out

    all_tickers = [t["ticker"] for t in actionable] + ["^GSPC"]
    prices = await asyncio.to_thread(_prices, all_tickers)
    spx_price = prices.get("^GSPC")

    saved = 0
    for trade in actionable:
        ticker = trade["ticker"]
        cat_date = None
        if trade.get("catalyst_date"):
            try:
                from datetime import date
                cat_date = date.fromisoformat(str(trade["catalyst_date"])[:10])
            except Exception:
                pass

        rec = AgentRecommendation(
            run_id=run_id,
            ticker=ticker,
            asset_class=trade.get("asset_class"),
            sector=trade.get("sector"),
            horizon=trade.get("horizon", "medium"),
            final_recommendation=trade["final_recommendation"],
            conviction=trade.get("conviction"),
            position_size_pct=trade.get("position_size_pct"),
            thesis=trade.get("suggested_action"),
            catalyst=trade.get("catalyst"),
            catalyst_date=cat_date,
            what_breaks_thesis=trade.get("what_breaks_thesis"),
            entry_price=prices.get(ticker),
            spx_entry_price=spx_price,
        )
        session.add(rec)
        saved += 1

    await session.commit()
    logger.info("Saved %d recommendations for run %s", saved, run_id)
    return saved


async def check_outcomes(session: AsyncSession) -> int:
    import yfinance as yf

    now = datetime.now(tz=UTC)
    rows = await session.execute(select(AgentRecommendation))
    recs = rows.scalars().all()

    pending = [
        r for r in recs
        if r.check_2w_price is None or r.check_4w_price is None or r.check_8w_price is None
    ]
    if not pending:
        return 0

    spx_price: float | None = None

    def _spx() -> float | None:
        try:
            return yf.Ticker("^GSPC").fast_info.last_price
        except Exception:
            return None

    updated = 0
    for rec in pending:
        entry = rec.entry_date
        if entry.tzinfo is None:
            entry = entry.replace(tzinfo=UTC)

        age = now - entry
        needs_any = (
            (rec.check_2w_price is None and age >= timedelta(weeks=2)) or
            (rec.check_4w_price is None and age >= timedelta(weeks=4)) or
            (rec.check_8w_price is None and age >= timedelta(weeks=8))
        )
        if not needs_any:
            continue

        if spx_price is None:
            spx_price = await asyncio.to_thread(_spx)

        def _get_price(tk: str) -> float | None:
            try:
                return yf.Ticker(tk).fast_info.last_price
            except Exception:
                return None

        price = await asyncio.to_thread(_get_price, rec.ticker)

        if rec.check_2w_price is None and age >= timedelta(weeks=2):
            rec.check_2w_price = price
            rec.check_2w_spx = spx_price
            rec.check_2w_date = now
            updated += 1

        if rec.check_4w_price is None and age >= timedelta(weeks=4):
            rec.check_4w_price = price
            rec.check_4w_spx = spx_price
            rec.check_4w_date = now
            updated += 1

        if rec.check_8w_price is None and age >= timedelta(weeks=8):
            rec.check_8w_price = price
            rec.check_8w_spx = spx_price
            rec.check_8w_date = now
            updated += 1

    if updated:
        await session.commit()
        logger.info("Updated %d outcome checks", updated)

    return updated


async def get_performance_summary(session: AsyncSession) -> dict[str, Any]:
    rows = await session.execute(select(AgentRecommendation).order_by(AgentRecommendation.entry_date.desc()))
    recs = rows.scalars().all()

    def _ret(price: Any, entry: Any) -> float | None:
        if price and entry and float(entry) > 0:
            return round((float(price) / float(entry) - 1) * 100, 2)
        return None

    records = []
    for r in recs:
        records.append({
            "id": r.id,
            "run_id": r.run_id,
            "ticker": r.ticker,
            "sector": r.sector,
            "horizon": r.horizon,
            "final_recommendation": r.final_recommendation,
            "conviction": r.conviction,
            "position_size_pct": float(r.position_size_pct) if r.position_size_pct else None,
            "thesis": r.thesis,
            "catalyst": r.catalyst,
            "catalyst_date": str(r.catalyst_date) if r.catalyst_date else None,
            "what_breaks_thesis": r.what_breaks_thesis,
            "entry_price": float(r.entry_price) if r.entry_price else None,
            "entry_date": r.entry_date.isoformat() if r.entry_date else None,
            "return_2w_pct": _ret(r.check_2w_price, r.entry_price),
            "return_4w_pct": _ret(r.check_4w_price, r.entry_price),
            "return_8w_pct": _ret(r.check_8w_price, r.entry_price),
            "spx_return_2w_pct": _ret(r.check_2w_spx, r.spx_entry_price),
            "spx_return_4w_pct": _ret(r.check_4w_spx, r.spx_entry_price),
            "spx_return_8w_pct": _ret(r.check_8w_spx, r.spx_entry_price),
            "check_2w_date": r.check_2w_date.isoformat() if r.check_2w_date else None,
            "check_4w_date": r.check_4w_date.isoformat() if r.check_4w_date else None,
            "check_8w_date": r.check_8w_date.isoformat() if r.check_8w_date else None,
        })

    total = len(records)
    with_2w = [r for r in records if r["return_2w_pct"] is not None]
    with_4w = [r for r in records if r["return_4w_pct"] is not None]

    def _avg(lst: list, key: str) -> float | None:
        vals = [r[key] for r in lst if r[key] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def _alpha(lst: list, ret_key: str, spx_key: str) -> float | None:
        alphas = [r[ret_key] - r[spx_key] for r in lst if r[ret_key] is not None and r[spx_key] is not None]
        return round(sum(alphas) / len(alphas), 2) if alphas else None

    return {
        "total_recommendations": total,
        "avg_return_2w_pct": _avg(with_2w, "return_2w_pct"),
        "avg_spx_return_2w_pct": _avg(with_2w, "spx_return_2w_pct"),
        "avg_alpha_2w_pct": _alpha(with_2w, "return_2w_pct", "spx_return_2w_pct"),
        "avg_return_4w_pct": _avg(with_4w, "return_4w_pct"),
        "avg_spx_return_4w_pct": _avg(with_4w, "spx_return_4w_pct"),
        "avg_alpha_4w_pct": _alpha(with_4w, "return_4w_pct", "spx_return_4w_pct"),
        "records": records,
    }
