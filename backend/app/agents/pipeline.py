"""Full agent pipeline orchestration."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import REDIS_AGENT_ANALYSIS_KEY, REDIS_AGENT_META_KEY, REDIS_PORTFOLIO_RISK_KEY
from app.core.config import get_settings
from app.core.redis_client import cache_load_json, cache_save_json
from app.db.session import async_session_factory
from app.services.paper_trading_service import sync_from_overseer
from app.services.recommendations_service import get_agent_calibration, save_recommendations

from .bear_case_agent import run_bear_case_agent
from .catalyst_agent import run_catalyst_agent
from .debate_agents import run_debate_round
from .memory import save_agent_memories
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

    # Phase 2 — catalyst + bear case in parallel
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

    # Load portfolio risk snapshot + agent calibration for overseer context
    risk_context = await cache_load_json(REDIS_PORTFOLIO_RISK_KEY)
    try:
        async with async_session_factory() as cal_session:
            calibration = await get_agent_calibration(cal_session)
    except Exception as exc:
        logger.warning("Agent calibration load failed: %s", exc)
        calibration = {}

    # Phase 3 — overseer (initial synthesis)
    logger.info("Phase 3: overseer initial synthesis (calibration for %d agents)", len(calibration))
    overseer_result = await run_overseer(
        sub_results, catalyst_result, bear_result, client, tool_context,
        risk_context=risk_context,
        agent_calibration=calibration,
    )

    # Phase 4 — debate round on STRONG_BUY / AVOID calls
    debate_results: dict[str, Any] = {"bull_debates": {}, "bear_rebuttals": {}}
    if overseer_result.error is None and overseer_result.parsed.get("verified_trades"):
        strong_buys = [
            t["ticker"] for t in overseer_result.parsed["verified_trades"]
            if t.get("final_recommendation") == "STRONG_BUY"
        ]
        avoids = [
            t["ticker"] for t in overseer_result.parsed["verified_trades"]
            if t.get("final_recommendation") == "AVOID"
        ]
        if strong_buys or avoids:
            logger.info(
                "Phase 4: debate round — %d STRONG_BUY, %d AVOID",
                len(strong_buys), len(avoids),
            )
            try:
                debate_results = await run_debate_round(
                    overseer_result.parsed,
                    bear_result.parsed if bear_result and not bear_result.error else {},
                    summaries,
                    client,
                    tool_context,
                )
                # Re-run overseer with debate context if debate produced results
                if debate_results["bull_debates"] or debate_results["bear_rebuttals"]:
                    logger.info("Phase 4b: overseer final synthesis with debate context")
                    overseer_result = await run_overseer(
                        sub_results, catalyst_result, bear_result, client, tool_context,
                        debate_context=debate_results,
                        risk_context=risk_context,
                        agent_calibration=calibration,
                    )
            except Exception as exc:
                logger.error("Debate round failed: %s", exc)

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
        "debate_report": debate_results,
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
        "debate_tickers": list(debate_results["bull_debates"].keys()) + list(debate_results["bear_rebuttals"].keys()),
    })

    # Save recommendations + agent memory (non-blocking failures)
    if overseer_result.error is None and overseer_result.parsed.get("verified_trades"):
        try:
            async with async_session_factory() as rec_session:
                await save_recommendations(run_id, overseer_result.parsed["verified_trades"], rec_session)
        except Exception as exc:
            logger.error("Failed to save recommendations: %s", exc)

    try:
        async with async_session_factory() as mem_session:
            await save_agent_memories(run_id, sub_results, mem_session)
    except Exception as exc:
        logger.error("Failed to save agent memories: %s", exc)

    if overseer_result.error is None and overseer_result.parsed.get("verified_trades"):
        try:
            async with async_session_factory() as pt_session:
                pt_result = await sync_from_overseer(
                    pt_session, overseer_result.parsed["verified_trades"], run_id
                )
            logger.info("Paper trading sync: opened=%s closed=%s", pt_result["opened"], pt_result["closed"])
        except Exception as exc:
            logger.error("Paper trading sync failed: %s", exc)

    logger.info(
        "Pipeline %s complete. overseer_ok=%s debate_tickers=%s",
        run_id, overseer_result.error is None, list(debate_results["bull_debates"].keys()),
    )
    return result
