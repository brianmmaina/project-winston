"""Job-status polling endpoints.

The frontend uses these to follow background tasks (refresh / retrain) so we
can show real progress instead of a fire-and-forget toast.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.jobs_service import get_job, recent_jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def api_get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await get_job(job_id, session=session)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return job


@router.get("")
async def api_recent_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    return await recent_jobs(session=session, limit=limit)
