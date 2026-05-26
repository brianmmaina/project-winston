"""Overseer agent — portfolio construction from all agent inputs."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import anthropic

from app.core.config import get_settings

from .base import AgentResult, run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_OVERSEER_SYSTEM = """You are the Portfolio Construction Overseer for XCE Advisor.

You receive reports from 11 sector agents, a catalyst agent (near-term event plays), and a bear case agent (risk challenges). Your job is to build a final PORTFOLIO — not just a list of picks.

## Decision framework

**STRONG_BUY** (position: 8-12% of portfolio)
- ML signal BUY + 2+ sector agents agree + catalyst agent confirms setup + bear case is weak + macro supports
- These are your highest-conviction, size-up positions

**BUY** (position: 4-7%)
- ML signal BUY + at least 1 relevant agent agrees + no major red flag from bear agent
- Solid thesis but less cross-confirmation

**HOLD** (position: 0-3% or existing position maintenance)
- Mixed signals, unclear catalyst timing, or bear case raises a valid concern not yet resolved

**AVOID**
- Bear case is strong, valuation is stretched, or macro regime is hostile. No position.

## Portfolio construction rules
- Total portfolio should have 3-5 SHORT-TERM plays (horizon: short, catalyst-driven, 1-4 weeks) and 5-8 MEDIUM-TERM positions (horizon: medium, structural, 1-3 months)
- Total positions: 8-13 names maximum
- Sector cap: no more than 25% in any single sector
- Theme cap: no more than 3 names in the same theme (e.g. not 4 AI semis)
- For short-term catalyst plays: use the catalyst agent's setup quality and options context — if options are already pricing in the move (IV/HV > 1.3), downgrade the position size
- Include what_breaks_thesis for every STRONG_BUY and BUY — this is the exit condition

## Output schema

Your final response must be a single JSON object (no other text):
{
  "market_overview": "<2-3 sentence macro context>",
  "portfolio_thesis": "<1-2 sentence overall portfolio positioning>",
  "verified_trades": [
    {
      "ticker": "<ticker>",
      "asset_class": "<commodity|stock>",
      "sector": "<sector name>",
      "ml_signal": "<BUY|HOLD>",
      "final_recommendation": "<STRONG_BUY|BUY|HOLD|AVOID>",
      "conviction": "<high|medium|low>",
      "horizon": "<short|medium>",
      "position_size_pct": <3-12 as number>,
      "agent_consensus": "<strong_agree|agree|mixed|disagree>",
      "catalyst": "<specific near-term catalyst or null>",
      "catalyst_date": "<YYYY-MM-DD or null>",
      "supporting_themes": ["<theme>"],
      "risk_factors": ["<risk>"],
      "what_breaks_thesis": "<specific condition that invalidates this trade>",
      "suggested_action": "<1 sentence specific entry instruction>"
    }
  ],
  "watchlist": [
    {"ticker": "<ticker>", "reason": "<why watching but not acting>", "trigger": "<what would make this actionable>"}
  ],
  "top_risks": ["<portfolio-level risk>"],
  "cross_asset_themes": ["<theme spanning asset classes>"],
  "generated_at": "<ISO timestamp>"
}
"""

_MAX_REPORT_CHARS = 2000


def _fmt(results: list[AgentResult]) -> str:
    parts = []
    for r in results:
        if r.error and not r.text:
            parts.append(f"[{r.name}]: FAILED — {r.error}")
        else:
            body = r.text[:_MAX_REPORT_CHARS]
            if len(r.text) > _MAX_REPORT_CHARS:
                body += "\n...[truncated]"
            parts.append(f"[{r.name}]:\n{body}")
    return "\n\n---\n\n".join(parts)


async def run_overseer(
    sub_results: list[AgentResult],
    catalyst_result: AgentResult | None,
    bear_result: AgentResult | None,
    client: anthropic.AsyncAnthropic,
    tool_context: ToolContext,
    debate_context: dict[str, Any] | None = None,
    risk_context: dict[str, Any] | None = None,
    agent_calibration: dict[str, float] | None = None,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    successful = sum(1 for r in sub_results if not r.error)
    report_block = _fmt(sub_results)

    catalyst_block = ""
    if catalyst_result and not catalyst_result.error:
        catalyst_block = f"\n\nCATALYST AGENT REPORT:\n{catalyst_result.text[:2000]}"

    bear_block = ""
    if bear_result and not bear_result.error:
        bear_block = f"\n\nBEAR CASE AGENT REPORT:\n{bear_result.text[:2000]}"

    debate_block = ""
    if debate_context and (debate_context.get("bull_debates") or debate_context.get("bear_rebuttals")):
        import json
        debate_block = f"\n\nDEBATE ROUND RESULTS:\n{json.dumps(debate_context, indent=2)[:3000]}"
        debate_block += (
            "\n\nIMPORTANT: A debate round was run on your STRONG_BUY and AVOID calls. "
            "Review the bull debate verdicts and bear rebuttal verdicts carefully before finalising. "
            "If a bull debate returns REDUCE_CONVICTION, downgrade STRONG_BUY → BUY. "
            "If a bear rebuttal returns RECONSIDER, upgrade AVOID → HOLD or BUY."
        )

    calibration_block = ""
    if agent_calibration:
        sorted_agents = sorted(agent_calibration.items(), key=lambda kv: kv[1], reverse=True)
        lines = [f"  {name}: {rate*100:.1f}% pick accuracy" for name, rate in sorted_agents]
        calibration_block = (
            "\n\nAGENT CALIBRATION (historical pick accuracy, 2w horizon):\n"
            + "\n".join(lines)
            + "\nINSTRUCTION: Weight higher-accuracy agents more when their picks align. "
            "If a low-accuracy agent is the sole advocate for a pick, treat it with more skepticism. "
            "Use this only as a soft prior — the current reports may still override historical performance."
        )

    risk_block = ""
    if risk_context:
        by_sec = ", ".join(f"{k}={v*100:.1f}%" for k, v in risk_context.get("by_sector", {}).items())
        flagged = ", ".join(risk_context.get("risk_flagged", [])) or "none"
        risk_block = (
            f"\n\nPORTFOLIO RISK SNAPSHOT (from ML risk layer):\n"
            f"  Total commodity exposure: {risk_context.get('commodity_exposure_pct', 0)*100:.1f}% "
            f"(limit {risk_context.get('limits', {}).get('max_commodity_pct', 0.4)*100:.0f}%)\n"
            f"  Total equity exposure: {risk_context.get('equity_exposure_pct', 0)*100:.1f}% "
            f"(limit {risk_context.get('limits', {}).get('max_equity_pct', 0.6)*100:.0f}%)\n"
            f"  By sector: {by_sec}\n"
            f"  Risk-flagged tickers (Kelly-adjusted): {flagged}\n"
            f"  Active BUY signals: {risk_context.get('buy_count', 0)}\n"
            "\nINSTRUCTION: Respect these sector and asset-class limits in your position_size_pct allocations. "
            "Tickers listed as risk-flagged have already had their ML-derived size reduced; treat them as lower conviction."
        )

    initial_message = (
        f"Today is {today}. Received reports from {successful}/{len(sub_results)} sector agents.\n\n"
        f"SECTOR AGENT REPORTS:\n{report_block}"
        f"{catalyst_block}"
        f"{bear_block}"
        f"{calibration_block}"
        f"{risk_block}"
        f"{debate_block}\n\n"
        "Your tasks:\n"
        "1. Use get_macro_indicators() to validate the macro backdrop\n"
        "2. Use get_commodity_signals() and get_stock_rankings() to spot-check any signal you want to verify\n"
        "3. Apply your portfolio construction rules — respect sector caps, theme caps, and position sizing\n"
        "4. Weight catalyst agent setups higher for short-horizon picks; weight sector agent conviction for medium-horizon\n"
        "5. Apply bear case objections — any pick flagged as 'picks_to_avoid' by the bear agent needs a strong counter-argument to include\n"
        + ("6. Review debate round verdicts and adjust conviction accordingly\n"
           "7. Output the final portfolio JSON" if debate_block else
           "6. Output the final portfolio JSON")
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
