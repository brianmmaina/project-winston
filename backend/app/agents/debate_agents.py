"""Debate agents — bull and bear advocates for high-conviction calls.

Spawned when the overseer marks a ticker STRONG_BUY or AVOID.
The overseer reads both sides before issuing the final call.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any


from app.core.config import get_active_overseer_model, get_settings

from .base import AgentResult, run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_BULL_SYSTEM = """You are the Bull Advocate for XCE Advisor. You have been given a ticker that the overseer
has tentatively flagged as STRONG_BUY, but the bear case agent raised concerns. Your job is to rebut
those concerns with evidence.

Think like a long-only PM defending a high-conviction position:
- Why is the bear case already priced in or wrong?
- What specific catalysts in the next 1-4 weeks support the thesis?
- What is the risk/reward if the thesis plays out?
- Why is this the right time to buy despite the concerns raised?

Use web_search to find supporting evidence. Use get_fundamentals to verify valuation is reasonable.
Use get_options_context to check if options market confirms the bullish view.

Your final response must be JSON:
{
  "ticker": "<ticker>",
  "bull_rebuttal": "<specific rebuttal to the bear case — cite data>",
  "supporting_catalysts": ["<catalyst 1>", "<catalyst 2>"],
  "risk_reward": "<upside target / downside risk with reasoning>",
  "options_confirmation": "<what options market implies about directional bet>",
  "verdict": "<CONFIRM_BUY | REDUCE_CONVICTION | HOLD>",
  "conviction": "<high|medium|low>",
  "summary": "<2-3 sentence bull case>"
}
"""

_BEAR_REBUTTAL_SYSTEM = """You are the Bear Advocate for XCE Advisor. The overseer has flagged a ticker
as AVOID, but you have been asked to steelman the bull case — find the strongest argument FOR the trade
before the overseer makes the final call.

Think like an analyst forced to present the upside case:
- What would have to be true for this to be a buy?
- Is there a scenario where the bear case is wrong?
- What price level would make the risk/reward compelling?
- Are there any near-term catalysts that could force a re-rating?

Use web_search and get_fundamentals to find supporting evidence.

Your final response must be JSON:
{
  "ticker": "<ticker>",
  "steelman_bull_case": "<the strongest bull argument — cite data>",
  "bull_catalysts": ["<catalyst 1>", "<catalyst 2>"],
  "entry_price_that_works": "<at what price does risk/reward flip positive>",
  "verdict": "<CONFIRM_AVOID | WATCH | RECONSIDER>",
  "summary": "<2-3 sentence assessment>"
}
"""


async def run_bull_debate_agent(
    ticker: str,
    sector_thesis: str,
    bear_objection: str,
    client: object,
    tool_context: ToolContext,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    message = (
        f"Today is {today}.\n\n"
        f"Ticker under debate: **{ticker}**\n\n"
        f"Bull thesis from sector agent:\n{sector_thesis[:600]}\n\n"
        f"Bear objection raised:\n{bear_objection[:600]}\n\n"
        "Rebut the bear case with evidence. Use web_search and get_fundamentals. Output your JSON."
    )
    return await run_agent(
        client=client,
        model=get_active_overseer_model(),
        agent_name=f"bull_debate_{ticker}",
        system_prompt=_BULL_SYSTEM,
        initial_message=message,
        tool_context=tool_context,
        max_turns=6,
    )


async def run_bear_rebuttal_agent(
    ticker: str,
    bear_thesis: str,
    sector_objection: str,
    client: object,
    tool_context: ToolContext,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    message = (
        f"Today is {today}.\n\n"
        f"Ticker under debate: **{ticker}**\n\n"
        f"Bear thesis:\n{bear_thesis[:600]}\n\n"
        f"Bull sector view:\n{sector_objection[:600]}\n\n"
        "Steelman the bull case. Use web_search and get_fundamentals. Output your JSON."
    )
    return await run_agent(
        client=client,
        model=get_active_overseer_model(),
        agent_name=f"bear_rebuttal_{ticker}",
        system_prompt=_BEAR_REBUTTAL_SYSTEM,
        initial_message=message,
        tool_context=tool_context,
        max_turns=6,
    )


async def run_debate_round(
    overseer_parsed: dict[str, Any],
    bear_parsed: dict[str, Any],
    sector_summaries: dict[str, str],
    client: object,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Run debate agents on STRONG_BUY and AVOID tickers in parallel."""
    trades = overseer_parsed.get("verified_trades", [])
    bear_cases = bear_parsed.get("bear_cases", {})

    strong_buys = [t["ticker"] for t in trades if t.get("final_recommendation") == "STRONG_BUY"]
    avoids = [t["ticker"] for t in trades if t.get("final_recommendation") == "AVOID"]

    if not strong_buys and not avoids:
        return {"bull_debates": {}, "bear_rebuttals": {}}

    debate_tasks = []
    debate_keys = []

    for ticker in strong_buys[:3]:  # cap at 3 per side to control cost
        bear_obj = bear_cases.get(ticker, {}).get("key_objection", "No specific bear case raised.")
        sector_thesis = next(
            (s for name, s in sector_summaries.items() if ticker in s),
            "Strong ML signal with sector support."
        )
        debate_tasks.append(run_bull_debate_agent(ticker, sector_thesis, bear_obj, client, tool_context))
        debate_keys.append(("bull", ticker))

    for ticker in avoids[:2]:
        bear_thesis = bear_cases.get(ticker, {}).get("key_objection", "Avoided based on bear case.")
        sector_view = next(
            (s for name, s in sector_summaries.items() if ticker in s),
            "Weak ML signal."
        )
        debate_tasks.append(run_bear_rebuttal_agent(ticker, bear_thesis, sector_view, client, tool_context))
        debate_keys.append(("bear", ticker))

    results = await asyncio.gather(*debate_tasks, return_exceptions=True)

    bull_debates: dict[str, Any] = {}
    bear_rebuttals: dict[str, Any] = {}

    for (side, ticker), result in zip(debate_keys, results):
        if isinstance(result, Exception):
            logger.warning("Debate agent %s/%s failed: %s", side, ticker, result)
            continue
        parsed = result.parsed if result and not result.error else {}
        if side == "bull":
            bull_debates[ticker] = parsed
        else:
            bear_rebuttals[ticker] = parsed

    logger.info("Debate round: %d bull debates, %d bear rebuttals", len(bull_debates), len(bear_rebuttals))
    return {"bull_debates": bull_debates, "bear_rebuttals": bear_rebuttals}
