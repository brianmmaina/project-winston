"""Sub-agent definitions and runners — 11 specialist agents covering all asset classes."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import anthropic

from app.core.config import get_settings

from .base import AgentResult, run_agent
from .tools import ToolContext

logger = logging.getLogger(__name__)

_OUTPUT_FORMAT = """
Your final response must be a single JSON object (no other text) with this structure:
{
  "agent": "<your agent name>",
  "summary": "<2-3 sentence market overview for your coverage area>",
  "signals": [
    {
      "ticker": "<ticker>",
      "name": "<full name>",
      "ml_signal": "<BUY or HOLD>",
      "agent_view": "<agree | cautious | disagree | neutral>",
      "conviction": "<high | medium | low>",
      "key_factors": ["<factor 1>", "..."],
      "risks": ["<risk 1>", "..."]
    }
  ],
  "top_picks": ["<ticker>", "..."],
  "caution_flags": ["<ticker or theme>", "..."],
  "news_highlights": ["<key headline or development>", "..."]
}
"""

_STEPS = (
    "Steps:\n"
    "1. Fetch the relevant ML signals for your coverage (get_commodity_signals or get_stock_rankings)\n"
    "2. Check macro indicators with get_macro_indicators\n"
    "3. Search for 2-3 most important recent developments using web_search\n"
    "4. Optionally check get_price_history or get_sentiment_scores for additional context\n\n"
    "Then output your JSON analysis."
)


@dataclass
class SubAgentSpec:
    name: str
    system_prompt: str
    coverage_desc: str


def _spec(name: str, role: str, coverage: str, focus: str) -> SubAgentSpec:
    system_prompt = (
        f"You are the {role} for XCE Advisor, an AI-powered trading research platform.\n"
        f"Coverage: {coverage}\n"
        f"Focus: {focus}\n\n"
        "Use your tools to gather current data before forming your assessment. "
        "Be specific and data-driven — cite actual figures you retrieved.\n"
        + _OUTPUT_FORMAT
    )
    return SubAgentSpec(name=name, system_prompt=system_prompt, coverage_desc=coverage)


# ---------------------------------------------------------------------------
# Commodity agents
# ---------------------------------------------------------------------------

ENERGY_AGENT = _spec(
    name="energy_commodities",
    role="Energy Commodities Analyst",
    coverage="Crude Oil WTI (CL=F), Natural Gas (NG=F), Heating Oil (HO=F), RBOB Gasoline (RB=F), Brent Crude (BZ=F)",
    focus=(
        "OPEC+ production decisions and compliance, US shale output and rig counts, "
        "seasonal demand patterns, LNG supply/demand balance, refinery utilisation, "
        "geopolitical risk in MENA and Russia, inventory levels (EIA reports)"
    ),
)

METALS_AGENT = _spec(
    name="metals",
    role="Metals Analyst",
    coverage="Gold (GC=F), Silver (SI=F), Copper (HG=F), Platinum (PL=F), Palladium (PA=F)",
    focus=(
        "Fed policy and real yields as gold/silver drivers, industrial demand for copper from China "
        "and the global EV/infrastructure buildout, auto-catalyst demand for platinum group metals, "
        "USD strength, physical ETF inflows/outflows, LME inventory levels"
    ),
)

AGRICULTURE_AGENT = _spec(
    name="agriculture",
    role="Agriculture Commodities Analyst",
    coverage="Corn (ZC=F), Wheat (ZW=F), Soybeans (ZS=F), Coffee (KC=F), Cotton (CT=F), Sugar (SB=F), Cocoa (CC=F)",
    focus=(
        "USDA crop reports and planted acreage estimates, La Niña/El Niño weather impacts, "
        "Black Sea grain export corridors, Brazil and Colombia crop conditions, "
        "biofuel mandates and ethanol demand for corn, global sugar production cycles"
    ),
)

# ---------------------------------------------------------------------------
# Stock sector agents (top-N from ML ranker, grouped by GICS)
# ---------------------------------------------------------------------------

TECH_COMMS_AGENT = _spec(
    name="tech_comms_stocks",
    role="Technology & Communications Equity Analyst",
    coverage="Information Technology and Communication Services stocks (use sector_group='tech_comms')",
    focus=(
        "AI/semiconductor capex cycle and hyperscaler spending, cloud revenue growth trends, "
        "digital advertising market (Meta, Alphabet), rate sensitivity of high-multiple growth stocks, "
        "earnings revision momentum, big-tech antitrust risk"
    ),
)

HEALTHCARE_AGENT = _spec(
    name="healthcare_stocks",
    role="Healthcare & Biotech Equity Analyst",
    coverage="Health Care sector stocks (use sector_group='healthcare')",
    focus=(
        "FDA pipeline catalysts and clinical trial readouts, GLP-1/weight-loss drug competitive landscape, "
        "Medicare/Medicaid reimbursement policy risk, biotech M&A activity, "
        "hospital utilisation and payer mix trends, generic drug pricing pressure"
    ),
)

FINANCIALS_AGENT = _spec(
    name="financials_stocks",
    role="Financials Equity Analyst",
    coverage="Financials sector stocks (use sector_group='financials')",
    focus=(
        "Net interest margin sensitivity to Fed rate path and deposit repricing, "
        "credit quality and loan loss reserve trends, investment banking deal flow recovery, "
        "insurance underwriting cycles and catastrophe exposure, "
        "fintech disruption of traditional banks, Basel III capital requirements"
    ),
)

CYCLICALS_AGENT = _spec(
    name="cyclicals_stocks",
    role="Cyclicals Equity Analyst",
    coverage="Industrials, Materials, and Energy sector stocks (use sector_group='cyclicals')",
    focus=(
        "Global manufacturing PMI and capex outlook, US reshoring and infrastructure spending, "
        "China industrial demand recovery, commodity input costs for materials companies, "
        "upstream energy company free cash flow vs WTI/Henry Hub spot prices, "
        "freight volumes and logistics pricing"
    ),
)

DEFENSIVES_AGENT = _spec(
    name="defensives_stocks",
    role="Defensives & Real Assets Equity Analyst",
    coverage=(
        "Consumer Discretionary, Consumer Staples, Utilities, and Real Estate sector stocks "
        "(use sector_group='defensives')"
    ),
    focus=(
        "Consumer confidence and spending bifurcation (high-end vs value), "
        "private label competition pressuring staples margins, "
        "utility rate case outcomes and renewable buildout capex, "
        "REIT rate sensitivity and cap rate expansion risk, "
        "housing market affordability and commercial real estate office vacancy"
    ),
)

# ---------------------------------------------------------------------------
# Cross-cutting agents
# ---------------------------------------------------------------------------

MACRO_RATES_AGENT = _spec(
    name="macro_rates",
    role="Macro & Rates Strategist",
    coverage="All asset classes — macro and rates overlay",
    focus=(
        "Fed funds rate path: current level, forward guidance, next FOMC meeting, "
        "yield curve shape (10y-2y spread) and recession probability, "
        "DXY strength impact on commodity prices and EM assets, "
        "inflation: CPI vs breakeven inflation expectations, "
        "VIX regime and cross-asset risk appetite"
    ),
)

GEOPOLITICS_AGENT = _spec(
    name="geopolitics",
    role="Geopolitics & Supply Chain Analyst",
    coverage="All asset classes — geopolitical and supply chain overlay",
    focus=(
        "Middle East tensions and risk to Strait of Hormuz oil flows, "
        "Russia-Ukraine war developments affecting energy and grain exports, "
        "US-China trade policy, tariffs, and technology export controls, "
        "sanctions regimes and their commodity market impact, "
        "global shipping disruptions (Red Sea, Panama Canal), "
        "election risks in major economies"
    ),
)

SENTIMENT_NEWS_AGENT = _spec(
    name="sentiment_news",
    role="Sentiment & News Flow Analyst",
    coverage="All commodities and top-ranked stocks",
    focus=(
        "Interpreting FinBERT sentiment scores in context of current news flow, "
        "identifying divergences between news sentiment and price action, "
        "detecting crowded positioning risks from unusual news volume spikes, "
        "social media and analyst sentiment shifts, "
        "earnings guidance tone vs quantitative signals"
    ),
)

ALL_SUB_AGENTS: list[SubAgentSpec] = [
    ENERGY_AGENT,
    METALS_AGENT,
    AGRICULTURE_AGENT,
    TECH_COMMS_AGENT,
    HEALTHCARE_AGENT,
    FINANCIALS_AGENT,
    CYCLICALS_AGENT,
    DEFENSIVES_AGENT,
    MACRO_RATES_AGENT,
    GEOPOLITICS_AGENT,
    SENTIMENT_NEWS_AGENT,
]


_CONCURRENCY = 3  # max simultaneous Anthropic API calls (Tier-1 rate limit safety)


async def run_sub_agent(
    spec: SubAgentSpec,
    client: anthropic.AsyncAnthropic,
    tool_context: ToolContext,
    sem: asyncio.Semaphore,
) -> AgentResult:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    initial_message = (
        f"Today is {today}. Conduct your analysis for: {spec.coverage_desc}\n\n" + _STEPS
    )
    async with sem:
        return await run_agent(
            client=client,
            model=get_settings().agent_model,
            agent_name=spec.name,
            system_prompt=spec.system_prompt,
            initial_message=initial_message,
            tool_context=tool_context,
            max_turns=8,
        )


async def run_all_sub_agents(
    client: anthropic.AsyncAnthropic,
    tool_context: ToolContext,
) -> list[AgentResult]:
    sem = asyncio.Semaphore(_CONCURRENCY)
    tasks = [run_sub_agent(spec, client, tool_context, sem) for spec in ALL_SUB_AGENTS]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[AgentResult] = []
    for spec, outcome in zip(ALL_SUB_AGENTS, raw):
        if isinstance(outcome, Exception):
            logger.error("Sub-agent %s raised: %s", spec.name, outcome)
            results.append(AgentResult(name=spec.name, text="", error=str(outcome)))
        else:
            results.append(outcome)
    return results
