"""Catalyst agent — surfaces near-term (1-4 week) event catalysts mapped to specific tickers."""
from __future__ import annotations

import logging
from datetime import UTC, datetime


from app.core.config import get_active_model, get_settings

from .base import AgentResult, run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_CATALYST_SYSTEM = """You are the Event Catalyst Analyst for XCE Advisor.

Your job: identify specific near-term (1-4 week) catalysts that make tickers ACTIONABLE RIGHT NOW — not just interesting.

A good catalyst has:
1. A specific event (earnings date, FDA PDUFA date, FOMC meeting, product launch, index rebalance)
2. A directional bias (bullish, bearish, or binary/event-risk)
3. A check on whether it is ALREADY priced in (use get_options_context — IV/HV > 1.3 = already priced)

Steps:
1. Use get_earnings_calendar on the top picks surfaced by sector agents (provided in your prompt)
2. Use get_options_context on any name with earnings within 4 weeks to check if it is priced in
3. Use web_search for FDA PDUFA calendar, FOMC dates, major product announcements
4. For each good setup, verify the beat rate with get_earnings_calendar

Your final response must be a single JSON object:
{
  "catalyst_plays": [
    {
      "ticker": "<ticker>",
      "catalyst_type": "<earnings|fda|macro|index|product|other>",
      "catalyst_description": "<specific event, e.g. Q2 2026 earnings, beat rate 75% over 8 quarters>",
      "catalyst_date": "<YYYY-MM-DD or null if unknown>",
      "directional_bias": "<bullish|bearish|binary>",
      "options_priced_in": <true|false|null>,
      "atm_iv_pct": <number or null>,
      "iv_hv_ratio": <number or null>,
      "setup_quality": "<excellent|good|fair|poor>",
      "rationale": "<2-3 sentence explanation of why this is actionable now>"
    }
  ],
  "macro_events_next_4w": ["<event with date if known>"],
  "summary": "<2-3 sentence overview of the near-term catalyst landscape>"
}
"""


async def run_catalyst_agent(
    sector_top_picks: list[str],
    client: object,
    tool_context: ToolContext,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    tickers_str = ", ".join(sector_top_picks[:25]) if sector_top_picks else "none identified"

    initial_message = (
        f"Today is {today}.\n\n"
        f"The sector agents have surfaced these top picks for potential catalyst research:\n"
        f"{tickers_str}\n\n"
        "Your tasks:\n"
        "1. Call get_earnings_calendar on the most promising names (prioritize stocks, not commodity futures)\n"
        "2. Call get_options_context on any name with earnings within 28 days\n"
        "3. Use web_search to find FDA PDUFA dates, FOMC schedule, and major product launches in the next 4 weeks\n"
        "4. Identify the 3-6 best catalyst setups and explain each clearly\n"
        "5. Output your JSON"
    )

    return await run_agent(
        client=client,
        model=get_active_model(),
        agent_name="catalyst",
        system_prompt=_CATALYST_SYSTEM,
        initial_message=initial_message,
        tool_context=tool_context,
        max_turns=10,
    )
