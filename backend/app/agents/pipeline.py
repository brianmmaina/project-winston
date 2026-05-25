"""Full agent pipeline orchestration."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import REDIS_AGENT_ANALYSIS_KEY, REDIS_AGENT_META_KEY
from app.core.config import get_settings
from app.core.redis_client import cache_save_json

from .overseer import run_overseer
from .sub_agents import ALL_SUB_AGENTS, run_all_sub_agents
from .tools import ToolContext

logger = logging.getLogger(__name__)


async def run_agent_pipeline(session: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured.")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    tool_context = ToolContext(session=session, top_n=settings.agent_top_n_per_sector)

    logger.info("Agent pipeline: running %d sub-agents in parallel", len(ALL_SUB_AGENTS))
    sub_results = await run_all_sub_agents(client, tool_context)

    successful = sum(1 for r in sub_results if not r.error)
    logger.info(
        "Sub-agents done: %d/%d succeeded. Starting overseer.", successful, len(sub_results)
    )

    overseer_result = await run_overseer(sub_results, client, tool_context)

    generated_at = datetime.now(tz=UTC).isoformat()
    result: dict[str, Any] = {
        "sub_reports": [
            {
                "name": r.name,
                "text": r.text,
                "parsed": r.parsed,
                "error": r.error,
            }
            for r in sub_results
        ],
        "overseer": {
            "text": overseer_result.text,
            "parsed": overseer_result.parsed,
            "error": overseer_result.error,
        },
        "generated_at": generated_at,
        "sub_agent_count": len(sub_results),
        "sub_agent_success_count": successful,
    }

    await cache_save_json(REDIS_AGENT_ANALYSIS_KEY, result)
    await cache_save_json(
        REDIS_AGENT_META_KEY,
        {
            "generated_at": generated_at,
            "sub_agent_count": len(sub_results),
            "sub_agent_success_count": successful,
            "overseer_ok": overseer_result.error is None,
        },
    )
    logger.info("Agent pipeline complete. Overseer ok=%s", overseer_result.error is None)
    return result
