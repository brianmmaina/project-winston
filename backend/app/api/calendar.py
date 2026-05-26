"""Calendar API — upcoming earnings and economic events."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.data.calendar_fetcher import (
    get_upcoming_earnings,
    get_upcoming_economic_events,
    ingest_earnings_calendar,
    ingest_economic_calendar,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/economic")
async def list_economic_events(
    days_ahead: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await get_upcoming_economic_events(session, days=days_ahead)


@router.get("/earnings")
async def list_earnings_events(
    days_ahead: int = Query(14, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await get_upcoming_earnings(session, days=days_ahead)


@router.post("/ingest/economic")
async def trigger_economic_ingest(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    n = await ingest_economic_calendar(session)
    return {"events_upserted": n}


@router.post("/ingest/earnings")
async def trigger_earnings_ingest(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from app.services.stocks_service import get_active_tickers
    tickers = await get_active_tickers(session)
    n = await ingest_earnings_calendar(session, tickers[:100])
    return {"events_upserted": n}
