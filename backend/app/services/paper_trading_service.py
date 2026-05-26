"""Paper trading service — simulates real trade execution against agent recommendations.

Rules:
- Starting capital: $100 000 (single portfolio, created on first use)
- Position sizing: uses overseer's position_size_pct (capped at 15 %)
- Stop loss: 8 % below entry (matches the live alert threshold)
- Auto-open: called from the agent pipeline after each overseer run
- Auto-close triggers: stop-loss breach, overseer AVOID/HOLD on open position,
  daily-scan "exit" action, or manual close via API
- Mark-to-market: daily scheduled job fetches live prices and checks stops
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaperPortfolio, PaperPosition, PaperTrade

logger = logging.getLogger(__name__)

INITIAL_CAPITAL = Decimal("100000.00")
STOP_LOSS_PCT = Decimal("0.08")          # 8 % below entry
MAX_POSITION_PCT = Decimal("0.15")       # hard cap per position
_OPEN_REC = {"STRONG_BUY", "BUY"}


# ---------------------------------------------------------------------------
# Portfolio bootstrap
# ---------------------------------------------------------------------------

async def get_or_create_portfolio(session: AsyncSession) -> PaperPortfolio:
    result = await session.execute(select(PaperPortfolio).limit(1))
    port = result.scalars().first()
    if port is None:
        spx_price = await _get_price("^GSPC")
        port = PaperPortfolio(
            initial_capital=INITIAL_CAPITAL,
            current_cash=INITIAL_CAPITAL,
            spx_entry_price=Decimal(str(spx_price)) if spx_price else None,
        )
        session.add(port)
        await session.flush()
    return port


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _fetch_price(ticker: str) -> float | None:
    try:
        import yfinance as yf
        return yf.Ticker(ticker).fast_info.last_price
    except Exception:
        return None


async def _get_price(ticker: str) -> float | None:
    return await asyncio.to_thread(_fetch_price, ticker)


# ---------------------------------------------------------------------------
# Open a position
# ---------------------------------------------------------------------------

async def open_position(
    session: AsyncSession,
    ticker: str,
    name: str | None,
    sector: str | None,
    asset_class: str | None,
    recommendation: str,
    conviction: str | None,
    position_size_pct: float,
    thesis: str | None,
    what_breaks_thesis: str | None,
    source_run_id: str | None,
) -> PaperPosition | None:
    """Buy a position if none is already open for this ticker."""
    # Skip if not actionable
    if recommendation not in _OPEN_REC:
        return None

    # Check duplicate
    existing = await session.execute(
        select(PaperPosition).where(PaperPosition.ticker == ticker, PaperPosition.is_open.is_(True))
    )
    if existing.scalars().first():
        logger.debug("Paper trade: %s already open, skipping", ticker)
        return None

    price = await _get_price(ticker)
    if not price or price <= 0:
        logger.warning("Paper trade: could not fetch price for %s", ticker)
        return None

    port = await get_or_create_portfolio(session)
    cash = float(port.current_cash)
    size_pct = min(float(position_size_pct) / 100.0, float(MAX_POSITION_PCT))
    capital = float(port.initial_capital)
    alloc = capital * size_pct
    if alloc > cash:
        alloc = cash * 0.95   # use available cash if tight
    if alloc < 100:
        logger.info("Paper trade: insufficient cash for %s (have $%.0f)", ticker, cash)
        return None

    shares = alloc / price
    stop_loss = price * (1.0 - float(STOP_LOSS_PCT))

    pos = PaperPosition(
        ticker=ticker,
        name=name,
        sector=sector,
        asset_class=asset_class,
        entry_price=Decimal(str(round(price, 4))),
        shares=Decimal(str(round(shares, 6))),
        position_size_pct=Decimal(str(round(size_pct * 100, 4))),
        stop_loss_price=Decimal(str(round(stop_loss, 4))),
        current_price=Decimal(str(round(price, 4))),
        recommendation=recommendation,
        conviction=conviction,
        thesis=thesis,
        what_breaks_thesis=what_breaks_thesis,
        source_run_id=source_run_id,
        is_open=True,
    )
    session.add(pos)

    trade = PaperTrade(
        ticker=ticker,
        direction="BUY",
        price=pos.entry_price,
        shares=pos.shares,
        value=Decimal(str(round(alloc, 2))),
        reason=f"agent:{recommendation.lower()}",
    )
    session.add(trade)

    port.current_cash = Decimal(str(round(cash - alloc, 2)))
    port.updated_at = datetime.now(tz=UTC)
    await session.flush()

    logger.info(
        "Paper BUY: %s @ $%.4f  shares=%.4f  alloc=$%.0f  cash_remaining=$%.0f",
        ticker, price, shares, alloc, float(port.current_cash),
    )
    return pos


# ---------------------------------------------------------------------------
# Close a position
# ---------------------------------------------------------------------------

async def close_position(
    session: AsyncSession,
    ticker: str,
    reason: str,
    price: float | None = None,
) -> PaperTrade | None:
    """Sell all shares of an open position."""
    result = await session.execute(
        select(PaperPosition).where(PaperPosition.ticker == ticker, PaperPosition.is_open.is_(True))
    )
    pos = result.scalars().first()
    if pos is None:
        return None

    if price is None:
        price = await _get_price(ticker)
    if not price or price <= 0:
        logger.warning("Paper close: could not fetch price for %s, using entry", ticker)
        price = float(pos.entry_price)

    shares = float(pos.shares)
    entry = float(pos.entry_price)
    proceeds = shares * price
    pnl_pct = round((price / entry - 1.0) * 100.0, 4)

    pos.is_open = False
    pos.closed_at = datetime.now(tz=UTC)
    pos.close_price = Decimal(str(round(price, 4)))
    pos.close_reason = reason
    pos.realized_pnl_pct = Decimal(str(pnl_pct))
    pos.current_price = Decimal(str(round(price, 4)))

    trade = PaperTrade(
        ticker=ticker,
        direction="SELL",
        price=Decimal(str(round(price, 4))),
        shares=pos.shares,
        value=Decimal(str(round(proceeds, 2))),
        pnl_pct=Decimal(str(pnl_pct)),
        reason=reason,
    )
    session.add(trade)

    port = await get_or_create_portfolio(session)
    port.current_cash += Decimal(str(round(proceeds, 2)))
    port.updated_at = datetime.now(tz=UTC)
    await session.flush()

    logger.info(
        "Paper SELL: %s @ $%.4f  pnl=%.2f%%  proceeds=$%.0f  cash_now=$%.0f",
        ticker, price, pnl_pct, proceeds, float(port.current_cash),
    )
    return trade


# ---------------------------------------------------------------------------
# Mark-to-market: update prices and fire stop losses
# ---------------------------------------------------------------------------

async def mark_to_market(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(PaperPosition).where(PaperPosition.is_open.is_(True))
    )
    positions = result.scalars().all()
    if not positions:
        return {"updated": 0, "stopped_out": []}

    stopped_out: list[str] = []

    for pos in positions:
        price = await _get_price(pos.ticker)
        if not price or price <= 0:
            continue
        pos.current_price = Decimal(str(round(price, 4)))

        if price <= float(pos.stop_loss_price):
            logger.info("Stop loss triggered: %s @ $%.4f (stop=%.4f)", pos.ticker, price, float(pos.stop_loss_price))
            await close_position(session, pos.ticker, reason="stop_loss", price=price)
            stopped_out.append(pos.ticker)

    port = await get_or_create_portfolio(session)
    port.updated_at = datetime.now(tz=UTC)

    return {"updated": len(positions), "stopped_out": stopped_out}


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------

async def get_portfolio_summary(session: AsyncSession) -> dict[str, Any]:
    port = await get_or_create_portfolio(session)

    open_result = await session.execute(
        select(PaperPosition).where(PaperPosition.is_open.is_(True))
    )
    open_positions = open_result.scalars().all()

    closed_result = await session.execute(
        select(PaperPosition).where(PaperPosition.is_open.is_(False))
    )
    closed_positions = closed_result.scalars().all()

    trades_result = await session.execute(
        select(PaperTrade).order_by(PaperTrade.traded_at.desc()).limit(100)
    )
    trades = trades_result.scalars().all()

    # Current portfolio value
    positions_value = sum(
        float(p.current_price or p.entry_price) * float(p.shares)
        for p in open_positions
    )
    total_value = float(port.current_cash) + positions_value
    total_pnl_pct = round((total_value / float(port.initial_capital) - 1.0) * 100.0, 2)

    # SPX benchmark return
    spx_current = await _get_price("^GSPC")
    spx_pnl_pct: float | None = None
    if spx_current and port.spx_entry_price:
        spx_pnl_pct = round((spx_current / float(port.spx_entry_price) - 1.0) * 100.0, 2)

    # Closed trade stats
    closed_pnls = [float(p.realized_pnl_pct) for p in closed_positions if p.realized_pnl_pct is not None]
    win_rate = round(sum(1 for x in closed_pnls if x > 0) / len(closed_pnls) * 100, 1) if closed_pnls else None
    avg_pnl = round(sum(closed_pnls) / len(closed_pnls), 2) if closed_pnls else None

    def _fmt_pos(p: PaperPosition) -> dict[str, Any]:
        current = float(p.current_price or p.entry_price)
        entry = float(p.entry_price)
        unrealized = round((current / entry - 1.0) * 100.0, 2)
        return {
            "id": p.id,
            "ticker": p.ticker,
            "name": p.name,
            "sector": p.sector,
            "asset_class": p.asset_class,
            "recommendation": p.recommendation,
            "conviction": p.conviction,
            "thesis": p.thesis,
            "what_breaks_thesis": p.what_breaks_thesis,
            "entry_price": float(p.entry_price),
            "entry_date": p.entry_date.isoformat() if p.entry_date else None,
            "shares": float(p.shares),
            "position_size_pct": float(p.position_size_pct),
            "stop_loss_price": float(p.stop_loss_price),
            "current_price": current,
            "unrealized_pnl_pct": unrealized,
            "position_value": round(current * float(p.shares), 2),
            "is_open": p.is_open,
            "close_reason": p.close_reason,
            "realized_pnl_pct": float(p.realized_pnl_pct) if p.realized_pnl_pct is not None else None,
        }

    def _fmt_trade(t: PaperTrade) -> dict[str, Any]:
        return {
            "id": t.id,
            "ticker": t.ticker,
            "direction": t.direction,
            "price": float(t.price),
            "shares": float(t.shares),
            "value": float(t.value),
            "pnl_pct": float(t.pnl_pct) if t.pnl_pct is not None else None,
            "reason": t.reason,
            "traded_at": t.traded_at.isoformat() if t.traded_at else None,
        }

    return {
        "portfolio": {
            "initial_capital": float(port.initial_capital),
            "current_cash": float(port.current_cash),
            "positions_value": round(positions_value, 2),
            "total_value": round(total_value, 2),
            "total_pnl_pct": total_pnl_pct,
            "spx_pnl_pct": spx_pnl_pct,
            "alpha_pct": round(total_pnl_pct - spx_pnl_pct, 2) if spx_pnl_pct is not None else None,
            "open_positions_count": len(open_positions),
            "closed_positions_count": len(closed_positions),
            "win_rate": win_rate,
            "avg_closed_pnl_pct": avg_pnl,
            "updated_at": port.updated_at.isoformat() if port.updated_at else None,
        },
        "open_positions": [_fmt_pos(p) for p in open_positions],
        "closed_positions": [_fmt_pos(p) for p in closed_positions],
        "trades": [_fmt_trade(t) for t in trades],
    }


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

async def reset_portfolio(session: AsyncSession) -> None:
    """Wipe all paper trading state and start fresh."""
    from sqlalchemy import delete
    await session.execute(delete(PaperTrade))
    await session.execute(delete(PaperPosition))
    await session.execute(delete(PaperPortfolio))
    await session.flush()
    await get_or_create_portfolio(session)
    logger.info("Paper portfolio reset to $%.0f", float(INITIAL_CAPITAL))


# ---------------------------------------------------------------------------
# Integration: called from agent pipeline after overseer run
# ---------------------------------------------------------------------------

async def sync_from_overseer(
    session: AsyncSession,
    verified_trades: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Open new positions for STRONG_BUY/BUY; close positions downgraded to AVOID."""
    opened: list[str] = []
    closed: list[str] = []

    # Collect tickers the overseer rated AVOID this run
    avoid_tickers = {
        t["ticker"] for t in verified_trades if t.get("final_recommendation") == "AVOID"
    }

    # Close any open positions that are now AVOID
    for ticker in avoid_tickers:
        trade = await close_position(session, ticker, reason="overseer_avoid")
        if trade:
            closed.append(ticker)

    # Open positions for new BUY/STRONG_BUY calls
    for trade in verified_trades:
        rec = trade.get("final_recommendation", "")
        if rec not in _OPEN_REC:
            continue
        pos = await open_position(
            session=session,
            ticker=trade["ticker"],
            name=trade.get("name"),
            sector=trade.get("sector"),
            asset_class=trade.get("asset_class"),
            recommendation=rec,
            conviction=trade.get("conviction"),
            position_size_pct=float(trade.get("position_size_pct") or 5.0),
            thesis=trade.get("suggested_action"),
            what_breaks_thesis=trade.get("what_breaks_thesis"),
            source_run_id=run_id,
        )
        if pos:
            opened.append(trade["ticker"])

    await session.commit()
    return {"opened": opened, "closed": closed}
