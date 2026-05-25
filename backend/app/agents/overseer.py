"""Overseer agent — synthesizes sub-agent reports into final verified recommendations."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import anthropic

from app.core.config import get_settings

from .base import AgentResult, run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_OVERSEER_SYSTEM = """You are the Chief Market Analyst (Overseer) for XCE Advisor, an AI-powered trading research platform.

Your role: synthesize findings from 11 specialist sub-agents covering commodities and equities, cross-check them against the ML pipeline signals, and produce the final verified trade recommendations.

Decision framework:
- STRONG_BUY: ML signal is BUY + 2 or more sub-agents agree + macro environment supports it
- BUY: ML signal is BUY + at least one relevant sub-agent agrees, no major red flags
- HOLD: ML signal is HOLD, or sub-agent signals are mixed, or you need more clarity
- AVOID: Sub-agents surface risks that materially override the ML signal

Your final response must be a single JSON object (no other text) with this structure:
{
  "market_overview": "<2-3 sentence global market context>",
  "verified_trades": [
    {
      "ticker": "<ticker>",
      "asset_class": "<commodity or stock>",
      "sector": "<e.g. Energy Commodities, Information Technology>",
      "ml_signal": "<BUY or HOLD>",
      "final_recommendation": "<STRONG_BUY | BUY | HOLD | AVOID>",
      "conviction": "<high | medium | low>",
      "agent_consensus": "<strong_agree | agree | mixed | disagree>",
      "supporting_themes": ["<theme 1>", "..."],
      "risk_factors": ["<risk 1>", "..."],
      "suggested_action": "<1 sentence specific action>"
    }
  ],
  "watchlist": [
    {"ticker": "<ticker>", "reason": "<why to watch but not act yet>"}
  ],
  "top_risks": ["<market-wide risk 1>", "..."],
  "cross_asset_themes": ["<theme spanning multiple asset classes>", "..."],
  "generated_at": "<ISO timestamp>"
}
"""

_MAX_REPORT_CHARS = 2500


def _format_sub_reports(results: list[AgentResult]) -> str:
    parts = []
    for r in results:
        if r.error and not r.text:
            parts.append(f"[{r.name}]: FAILED — {r.error}")
        else:
            body = r.text[:_MAX_REPORT_CHARS]
            if len(r.text) > _MAX_REPORT_CHARS:
                body += "\n... [truncated]"
            parts.append(f"[{r.name}]:\n{body}")
    return "\n\n---\n\n".join(parts)


async def run_overseer(
    sub_results: list[AgentResult],
    client: anthropic.AsyncAnthropic,
    tool_context: ToolContext,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    successful = sum(1 for r in sub_results if not r.error)
    report_block = _format_sub_reports(sub_results)

    initial_message = (
        f"Today is {today}. You have received reports from {successful}/{len(sub_results)} specialist agents.\n\n"
        f"SUB-AGENT REPORTS:\n{report_block}\n\n"
        "Your tasks:\n"
        "1. Use get_commodity_signals() to independently verify the commodity ML signals\n"
        "2. Use get_stock_rankings() to cross-check any stock sectors you want to verify\n"
        "3. Use get_macro_indicators() to validate the macro context agents described\n"
        "4. Use web_search() to fact-check any high-impact claim before issuing a STRONG_BUY or AVOID\n"
        "5. Produce the final verified JSON recommendations — focus on the highest-conviction opportunities "
        "and the most important risks. Only include tickers where you have a clear view."
    )

    return await run_agent(
        client=client,
        model=get_settings().agent_overseer_model,
        agent_name="overseer",
        system_prompt=_OVERSEER_SYSTEM,
        initial_message=initial_message,
        tool_context=tool_context,
        max_turns=15,
    )
