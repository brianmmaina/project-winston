"""Manual data ingest triggers — COT, EIA."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.data.cot_fetcher import ingest_cot_data
from app.data.eia_fetcher import ingest_eia_data
from app.data.usda_fetcher import ingest_usda

router = APIRouter(prefix="/api/data", tags=["data-ingest"])


@router.post("/ingest/cot")
async def trigger_cot_ingest(
    years_back: int = 2,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    n = await ingest_cot_data(session, years_back=years_back)
    return {"rows_upserted": n}


@router.post("/ingest/eia")
async def trigger_eia_ingest(
    weeks_back: int = 104,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    n = await ingest_eia_data(session, weeks_back=weeks_back)
    return {"rows_upserted": n}


@router.post("/ingest/usda")
async def trigger_usda_ingest(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await ingest_usda(session)
