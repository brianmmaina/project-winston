"""Market alerts API — price spike and event-driven alerts."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.alerts_service import acknowledge_alert, check_price_alerts, get_recent_alerts

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    limit: int = 50,
    unacked_only: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await get_recent_alerts(session, limit=limit, unacked_only=unacked_only)


@router.post("/scan")
async def trigger_alert_scan(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    n = await check_price_alerts(session)
    return {"alerts_triggered": n}


@router.post("/{alert_id}/acknowledge")
async def ack_alert(alert_id: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    ok = await acknowledge_alert(session, alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": True}
