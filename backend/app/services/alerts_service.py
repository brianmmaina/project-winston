"""Market alerts service — price spike detection and event-driven alerts."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import yfinance as yf
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COMMODITIES
from app.db.models import AgentRecommendation, CommodityPrice, MarketAlert, StockPrice

logger = logging.getLogger(__name__)

_INTRADAY_SPIKE_PCT = 2.5    # % move in one day triggers alert
_WEEKLY_SPIKE_PCT = 5.0      # % move in 5 days triggers alert
_POSITION_ALERT_PCT = 5.0    # % move against open recommendation
_STOP_LOSS_PCT = 8.0         # hard stop-loss threshold


def _pct(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / abs(old) * 100


async def _get_recent_prices(session: AsyncSession, ticker: str, days: int = 10) -> list[tuple[date, float]]:
    cutoff = date.today() - timedelta(days=days)
    if ticker in COMMODITIES:
        q = await session.execute(
            select(CommodityPrice.date, CommodityPrice.close)
            .where(CommodityPrice.ticker == ticker, CommodityPrice.date >= cutoff)
            .order_by(CommodityPrice.date)
        )
    else:
        q = await session.execute(
            select(StockPrice.date, StockPrice.close)
            .where(StockPrice.ticker == ticker, StockPrice.date >= cutoff)
            .order_by(StockPrice.date)
        )
    return [(r[0], float(r[1])) for r in q.all() if r[1] is not None]


async def _create_alert(session: AsyncSession, ticker: str, alert_type: str, severity: str,
                        message: str, price: float | None = None, change_pct: float | None = None) -> None:
    alert = MarketAlert(
        ticker=ticker,
        alert_type=alert_type,
        severity=severity,
        triggered_at=datetime.now(tz=UTC),
        message=message,
        price=Decimal(str(round(price, 4))) if price is not None else None,
        change_pct=Decimal(str(round(change_pct, 4))) if change_pct is not None else None,
    )
    session.add(alert)


async def check_price_alerts(session: AsyncSession) -> int:
    """Check all tracked tickers for significant price moves. Returns alert count."""
    alert_count = 0
    all_tickers = list(COMMODITIES.keys())

    # Also check open agent recommendations
    q = await session.execute(
        select(AgentRecommendation.ticker, AgentRecommendation.entry_price)
        .where(
            AgentRecommendation.final_recommendation.in_(["BUY", "STRONG_BUY"]),
            AgentRecommendation.check_4w_price.is_(None),
        )
        .distinct()
    )
    rec_tickers = {row[0]: float(row[1]) for row in q.all() if row[1]}
    all_tickers = list(set(all_tickers + list(rec_tickers.keys())))

    for ticker in all_tickers:
        try:
            prices = await _get_recent_prices(session, ticker, days=10)
            if len(prices) < 2:
                continue

            latest_date, latest_price = prices[-1]
            prev_date, prev_price = prices[-2]
            week_ago_price = prices[0][1] if len(prices) >= 5 else prev_price

            # 1-day spike
            daily_chg = _pct(latest_price, prev_price)
            if abs(daily_chg) >= _INTRADAY_SPIKE_PCT:
                direction = "surged" if daily_chg > 0 else "dropped"
                severity = "high" if abs(daily_chg) >= 5 else "medium"
                await _create_alert(
                    session, ticker, "price_spike", severity,
                    f"{ticker} {direction} {daily_chg:+.1f}% on {latest_date} (${latest_price:.2f})",
                    latest_price, daily_chg,
                )
                alert_count += 1

            # 5-day move
            weekly_chg = _pct(latest_price, week_ago_price)
            if abs(weekly_chg) >= _WEEKLY_SPIKE_PCT and abs(daily_chg) < _INTRADAY_SPIKE_PCT:
                direction = "up" if weekly_chg > 0 else "down"
                await _create_alert(
                    session, ticker, "weekly_move", "medium",
                    f"{ticker} moved {weekly_chg:+.1f}% over 5 days to ${latest_price:.2f}",
                    latest_price, weekly_chg,
                )
                alert_count += 1

            # Open position adverse move
            if ticker in rec_tickers:
                entry = rec_tickers[ticker]
                move_vs_entry = _pct(latest_price, entry)
                if move_vs_entry <= -_POSITION_ALERT_PCT:
                    await _create_alert(
                        session, ticker, "position_adverse", "high",
                        f"Open {ticker} position down {move_vs_entry:.1f}% from entry (${entry:.2f} → ${latest_price:.2f})",
                        latest_price, move_vs_entry,
                    )
                    alert_count += 1

                # Hard stop-loss breach
                if move_vs_entry <= -_STOP_LOSS_PCT:
                    # Deduplicate: skip if unacknowledged stop_loss_breach exists in last 48h
                    cutoff_48h = datetime.now(tz=UTC) - timedelta(hours=48)
                    dup_q = await session.execute(
                        select(MarketAlert).where(
                            MarketAlert.ticker == ticker,
                            MarketAlert.alert_type == "stop_loss_breach",
                            MarketAlert.acknowledged.is_(False),
                            MarketAlert.triggered_at >= cutoff_48h,
                        ).limit(1)
                    )
                    if dup_q.scalars().first() is None:
                        await _create_alert(
                            session, ticker, "stop_loss_breach", "high",
                            f"STOP LOSS: {ticker} is {abs(move_vs_entry):.1f}% below entry of ${entry:.2f} (now ${latest_price:.2f})",
                            latest_price, move_vs_entry,
                        )
                        alert_count += 1

        except Exception as exc:
            logger.debug("Alert check failed for %s: %s", ticker, exc)

    if alert_count:
        await session.commit()
    logger.info("Price alert scan: %d alerts triggered", alert_count)
    return alert_count


async def get_recent_alerts(session: AsyncSession, limit: int = 50, unacked_only: bool = False) -> list[dict[str, Any]]:
    stmt = select(MarketAlert).order_by(desc(MarketAlert.triggered_at)).limit(limit)
    if unacked_only:
        stmt = stmt.where(MarketAlert.acknowledged.is_(False))
    q = await session.execute(stmt)
    rows = q.scalars().all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "alert_type": r.alert_type,
            "severity": r.severity,
            "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
            "message": r.message,
            "price": float(r.price) if r.price is not None else None,
            "change_pct": float(r.change_pct) if r.change_pct is not None else None,
            "acknowledged": r.acknowledged,
        }
        for r in rows
    ]


async def acknowledge_alert(session: AsyncSession, alert_id: int) -> bool:
    q = await session.execute(select(MarketAlert).where(MarketAlert.id == alert_id))
    alert = q.scalars().first()
    if alert is None:
        return False
    alert.acknowledged = True
    alert.acknowledged_at = datetime.now(tz=UTC)
    await session.commit()
    return True
