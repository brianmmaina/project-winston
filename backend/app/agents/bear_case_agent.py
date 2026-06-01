"""Bear case agent — adversarially challenges picks before the overseer sees them."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any


from app.core.config import get_active_model, get_settings

from .base import AgentResult, run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_BEAR_SYSTEM = """You are the Bear Case Analyst for XCE Advisor. Your ONLY job is to find problems with proposed trades.

Think like a short seller. For each ticker under review:
- What is ALREADY priced in that the bulls are ignoring?
- What is the single strongest argument against this trade?
- What macro regime or specific event would destroy the thesis?
- Is valuation stretched relative to sector peers or own history?
- Is this a crowded consensus trade that could reverse violently?
- Are there any red flags in recent earnings quality, guidance, or insider activity?

Use get_fundamentals to check valuations. Use web_search to find the bearish narrative on each name.
Use get_estimate_revisions to catch names where analysts are quietly downgrading despite bullish price action.

Be specific and data-driven. Vague concerns are worthless — cite actual multiples, specific risks, or concrete events.

Your final response must be a single JSON object:
{
  "bear_cases": {
    "<ticker>": {
      "strength": "<high|medium|low>",
      "key_objection": "<the single strongest bear argument — be specific>",
      "what_breaks_thesis": "<the specific condition that invalidates the bull case>",
      "valuation_concern": "<is the stock expensive vs history/peers? cite multiples>",
      "crowding_risk": "<is this a consensus trade? what is the crowded exit risk?>",
      "downgrade_risk": "<any signs analysts are turning cautious?>"
    }
  },
  "highest_risk_picks": ["<ticker ranked by bear case strength>"],
  "picks_to_avoid": ["<tickers you believe should be removed from consideration>"],
  "summary": "<2-3 sentence overall risk assessment>"
}
"""


async def run_bear_case_agent(
    sector_top_picks: list[str],
    sector_summaries: dict[str, Any],
    client: object,
    tool_context: ToolContext,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    tickers_str = ", ".join(sector_top_picks[:20])

    summaries_block = "\n".join(
        f"[{name}]: {summary[:300]}" for name, summary in list(sector_summaries.items())[:6]
    )

    initial_message = (
        f"Today is {today}.\n\n"
        f"The sector agents are proposing these tickers as potential buys:\n{tickers_str}\n\n"
        f"Key sector agent summaries:\n{summaries_block}\n\n"
        "Your tasks:\n"
        "1. Use get_fundamentals on the top 5-8 names to check if valuations are stretched\n"
        "2. Use get_estimate_revisions to catch any names with hidden downgrade momentum\n"
        "3. Use web_search to find the bear thesis on the 3-4 most consensus picks\n"
        "4. For each name, generate the strongest possible bear case\n"
        "5. Identify which picks you believe are the highest risk and which should be avoided\n"
        "6. Output your JSON"
    )

    return await run_agent(
        client=client,
        model=get_active_model(),
        agent_name="bear_case",
        system_prompt=_BEAR_SYSTEM,
        initial_message=initial_message,
        tool_context=tool_context,
        max_turns=10,
    )
