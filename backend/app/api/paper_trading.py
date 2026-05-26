"""Paper trading API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_session
from app.core.security import require_api_key
from app.services.paper_trading_service import (
    close_position,
    get_portfolio_summary,
    mark_to_market,
    open_position,
    reset_portfolio,
)

router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])


class OpenPositionRequest(BaseModel):
    ticker: str
    recommendation: str = "BUY"
    position_size_pct: float = Field(default=5.0, ge=0.5, le=15.0)
    thesis: str | None = None


@router.post("/open", dependencies=[Depends(require_api_key)])
async def api_open_position(req: OpenPositionRequest, session=Depends(get_session)) -> dict[str, Any]:
    ticker = req.ticker.strip().upper()
    if req.recommendation not in {"BUY", "STRONG_BUY"}:
        raise HTTPException(status_code=422, detail="recommendation must be BUY or STRONG_BUY")
    pos = await open_position(
        session=session,
        ticker=ticker,
        name=None,
        sector=None,
        asset_class=None,
        recommendation=req.recommendation,
        conviction=None,
        position_size_pct=req.position_size_pct,
        thesis=req.thesis or None,
        what_breaks_thesis=None,
        source_run_id="manual",
    )
    if pos is None:
        raise HTTPException(
            status_code=400,
            detail=f"Could not open {ticker} — already open, insufficient cash, or price unavailable",
        )
    await session.commit()
    return {
        "opened": pos.ticker,
        "entry_price": float(pos.entry_price),
        "shares": float(pos.shares),
        "position_size_pct": float(pos.position_size_pct),
    }


@router.get("/portfolio")
async def api_get_portfolio(session=Depends(get_session)) -> dict[str, Any]:
    return await get_portfolio_summary(session)


@router.post("/mark-to-market", dependencies=[Depends(require_api_key)])
async def api_mark_to_market(session=Depends(get_session)) -> dict[str, Any]:
    result = await mark_to_market(session)
    await session.commit()
    return result


@router.post("/close/{ticker}", dependencies=[Depends(require_api_key)])
async def api_close_position(ticker: str, session=Depends(get_session)) -> dict[str, Any]:
    trade = await close_position(session, ticker.upper(), reason="manual")
    if trade is None:
        raise HTTPException(status_code=404, detail=f"No open position for {ticker}")
    await session.commit()
    return {"closed": ticker.upper(), "pnl_pct": float(trade.pnl_pct) if trade.pnl_pct else None}


@router.post("/reset", dependencies=[Depends(require_api_key)])
async def api_reset_portfolio(session=Depends(get_session)) -> dict[str, Any]:
    await reset_portfolio(session)
    await session.commit()
    return {"reset": True, "initial_capital": 100000}
