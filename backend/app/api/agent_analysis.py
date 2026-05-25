"""API endpoints for the multi-agent market analysis pipeline."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.constants import REDIS_AGENT_ANALYSIS_KEY, REDIS_AGENT_META_KEY
from app.core.config import get_settings
from app.core.redis_client import cache_load_json
from app.core.security import require_api_key
from app.db.session import async_session_factory
from app.services.jobs_service import complete_job, fail_job, mark_running, start_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-analysis", tags=["agent-analysis"])


class AgentJobResponse(BaseModel):
    job_id: str
    status: str
    name: str


async def _run_pipeline_task(job_id: str) -> None:
    try:
        from app.agents.pipeline import run_agent_pipeline

        await mark_running(job_id, "starting agent pipeline — 11 sub-agents + overseer")
        async with async_session_factory() as session:
            result = await run_agent_pipeline(session)
        overseer_ok = result["overseer"]["error"] is None
        await complete_job(
            job_id,
            f"sub_agents={result['sub_agent_success_count']}/{result['sub_agent_count']} overseer_ok={overseer_ok}",
        )
    except Exception as exc:
        logger.exception("Agent pipeline job %s failed", job_id)
        await fail_job(job_id, str(exc)[:512])


@router.post("", response_model=AgentJobResponse, dependencies=[Depends(require_api_key)])
async def start_agent_analysis(background_tasks: BackgroundTasks) -> AgentJobResponse:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Agent analysis requires ANTHROPIC_API_KEY to be configured in the environment.",
        )
    job_id = await start_job("agent_analysis")
    background_tasks.add_task(_run_pipeline_task, job_id)
    return AgentJobResponse(job_id=job_id, status="pending", name="agent_analysis")


@router.get("/latest")
async def get_latest_analysis() -> dict[str, Any]:
    data = await cache_load_json(REDIS_AGENT_ANALYSIS_KEY)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="No agent analysis available yet. Run POST /api/agent-analysis first.",
        )
    return data


@router.get("/meta")
async def get_analysis_meta() -> dict[str, Any]:
    meta = await cache_load_json(REDIS_AGENT_META_KEY)
    if meta is None:
        raise HTTPException(status_code=404, detail="No agent analysis metadata available.")
    return meta
