"""Full agent pipeline orchestration."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import REDIS_AGENT_ANALYSIS_KEY, REDIS_AGENT_META_KEY
from app.core.config import get_settings
from app.core.redis_client import cache_save_json
from app.db.session import async_session_factory
from app.services.recommendations_service import save_recommendations

from .bear_case_agent import run_bear_case_agent
from .catalyst_agent import run_catalyst_agent
from .overseer import run_overseer
from .sub_agents import ALL_SUB_AGENTS, run_all_sub_agents
from .tools import ToolContext

logger = logging.getLogger(__name__)


def _collect_top_picks(sub_results: list) -> list[str]:
    seen: set[str] = set()
    picks: list[str] = []
    for r in sub_results:
        if r.error:
            continue
        for tk in r.parsed.get("top_picks", []):
            if tk not in seen:
                seen.add(tk)
                picks.append(tk)
    return picks


def _collect_summaries(sub_results: list) -> dict[str, str]:
    return {r.name: r.parsed.get("summary", r.text[:200]) for r in sub_results if not r.error}


async def run_agent_pipeline(session: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured.")

    run_id = str(uuid.uuid4())
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    tool_context = ToolContext(session=session, top_n=settings.agent_top_n_per_sector)

    # Phase 1 — sector agents in parallel (semaphore-limited)
    logger.info("Pipeline %s: running %d sector agents", run_id, len(ALL_SUB_AGENTS))
    sub_results = await run_all_sub_agents(client, tool_context)
    successful = sum(1 for r in sub_results if not r.error)
    logger.info("Sector agents done: %d/%d succeeded", successful, len(sub_results))

    # Phase 2 — catalyst + bear case in parallel (depend only on sector output)
    top_picks = _collect_top_picks(sub_results)
    summaries = _collect_summaries(sub_results)
    logger.info("Phase 2: catalyst + bear case agents on %d picks", len(top_picks))

    catalyst_result, bear_result = await asyncio.gather(
        run_catalyst_agent(top_picks, client, tool_context),
        run_bear_case_agent(top_picks, summaries, client, tool_context),
        return_exceptions=True,
    )
    if isinstance(catalyst_result, Exception):
        logger.error("Catalyst agent failed: %s", catalyst_result)
        catalyst_result = None
    if isinstance(bear_result, Exception):
        logger.error("Bear case agent failed: %s", bear_result)
        bear_result = None

    # Phase 3 — overseer
    logger.info("Phase 3: overseer")
    overseer_result = await run_overseer(sub_results, catalyst_result, bear_result, client, tool_context)

    generated_at = datetime.now(tz=UTC).isoformat()
    result: dict[str, Any] = {
        "run_id": run_id,
        "sub_reports": [
            {"name": r.name, "text": r.text, "parsed": r.parsed, "error": r.error}
            for r in sub_results
        ],
        "catalyst_report": {
            "text": catalyst_result.text if catalyst_result else "",
            "parsed": catalyst_result.parsed if catalyst_result else {},
            "error": catalyst_result.error if catalyst_result else "agent_failed",
        },
        "bear_report": {
            "text": bear_result.text if bear_result else "",
            "parsed": bear_result.parsed if bear_result else {},
            "error": bear_result.error if bear_result else "agent_failed",
        },
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
    await cache_save_json(REDIS_AGENT_META_KEY, {
        "run_id": run_id,
        "generated_at": generated_at,
        "sub_agent_count": len(sub_results),
        "sub_agent_success_count": successful,
        "overseer_ok": overseer_result.error is None,
        "catalyst_ok": catalyst_result is not None and catalyst_result.error is None,
        "bear_case_ok": bear_result is not None and bear_result.error is None,
    })

    # Phase 4 — save recommendations for outcome tracking (non-blocking failure)
    if overseer_result.error is None and overseer_result.parsed.get("verified_trades"):
        try:
            async with async_session_factory() as rec_session:
                await save_recommendations(run_id, overseer_result.parsed["verified_trades"], rec_session)
        except Exception as exc:
            logger.error("Failed to save recommendations: %s", exc)

    logger.info("Pipeline %s complete. overseer_ok=%s", run_id, overseer_result.error is None)
    return result
