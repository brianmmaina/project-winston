"""Lightweight Haiku daily scan — monitors existing picks for thesis-breaking developments."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import anthropic

from app.constants import REDIS_AGENT_ANALYSIS_KEY, REDIS_DAILY_SCAN_KEY
from app.core.redis_client import cache_load_json, cache_save_json
from app.db.session import async_session_factory

from .base import run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_SCAN_SYSTEM = """You are a portfolio monitor for XCE Advisor performing a daily health check.

Review the current portfolio picks provided and answer ONE question for each:
Has anything materially changed since this pick was made that would cause us to exit or reduce the position?

Be terse, specific, and decisive. Only flag if something is genuinely actionable — do not flag normal market noise.
A 2% move on a medium-term position is NOT worth flagging. A guidance cut, earnings miss, or thesis-breaking news IS.

For each concern, specify: exit (close the position), reduce (cut size by half), hold (no action), or add (add to position on the dip).

Respond with a single JSON object:
{
  "alerts": [
    {
      "ticker": "<ticker>",
      "severity": "<high|medium|low>",
      "alert": "<specific issue — cite actual news or data>",
      "action": "<exit|reduce|hold|add>",
      "rationale": "<1 sentence>"
    }
  ],
  "portfolio_health": "<healthy|some_concerns|deteriorating>",
  "market_note": "<1 sentence on the overall market environment today>",
  "scanned_at": "<ISO timestamp>"
}
"""


async def run_daily_scan() -> dict[str, Any]:
    latest = await cache_load_json(REDIS_AGENT_ANALYSIS_KEY)
    if not latest:
        return {"skipped": True, "reason": "No analysis available to scan"}

    overseer = latest.get("overseer", {})
    parsed = overseer.get("parsed", {})
    trades = parsed.get("verified_trades", [])
    active_picks = [t for t in trades if t.get("final_recommendation") in ("STRONG_BUY", "BUY")]

    if not active_picks:
        return {"skipped": True, "reason": "No active BUY picks to monitor"}

    from app.core.config import get_settings
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"skipped": True, "reason": "No ANTHROPIC_API_KEY configured"}

    picks_summary = "\n".join(
        f"- {p['ticker']} ({p.get('horizon','?')}-term, {p.get('final_recommendation')}): "
        f"{p.get('suggested_action','')[:120]} | breaks if: {p.get('what_breaks_thesis','?')[:100]}"
        for p in active_picks
    )

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    initial_message = (
        f"Today is {today}. Current active portfolio picks:\n{picks_summary}\n\n"
        "Tasks:\n"
        "1. Use web_search for any recent news on these tickers (search '[ticker] news today' for 2-3 highest-risk names)\n"
        "2. Flag only genuine thesis-breaking developments\n"
        "3. Output your JSON health check"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    haiku_model = "claude-haiku-4-5-20251001"

    async with async_session_factory() as session:
        tool_context = ToolContext(session=session, top_n=10)
        result = await run_agent(
            client=client,
            model=haiku_model,
            agent_name="daily_scan",
            system_prompt=_SCAN_SYSTEM,
            initial_message=initial_message,
            tool_context=tool_context,
            max_turns=6,
        )

    output = result.parsed if result.parsed else {}
    output["scanned_at"] = datetime.now(tz=UTC).isoformat()
    output["active_picks_count"] = len(active_picks)

    await cache_save_json(REDIS_DAILY_SCAN_KEY, output)
    logger.info("Daily scan complete — health: %s, alerts: %d", output.get("portfolio_health"), len(output.get("alerts", [])))
    return output
