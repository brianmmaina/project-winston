"""Tool schemas and implementations for the agent layer."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import REDIS_SIGNAL_FILTERED_KEY
from app.core.config import get_settings
from app.core.redis_client import cache_load_json
from app.db.models import (
    CommodityPrice,
    MacroIndicator,
    PortfolioRanking,
    SentimentScore,
    StockPrice,
)

logger = logging.getLogger(__name__)

SECTOR_GROUPS: dict[str, list[str]] = {
    "tech_comms": ["Information Technology", "Communication Services"],
    "healthcare": ["Health Care"],
    "financials": ["Financials"],
    "cyclicals": ["Industrials", "Materials", "Energy"],
    "defensives": ["Consumer Discretionary", "Consumer Staples", "Utilities", "Real Estate"],
}

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "web_search",
        "description": (
            "Search the web for live market news, economic data releases, OPEC decisions, "
            "earnings reports, and geopolitical events. Use for current information beyond the database."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Be specific — include asset names, dates, events.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (1-10, default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_commodity_signals",
        "description": (
            "Get the latest ML-generated signals for all 17 commodity futures. "
            "Returns ticker, signal (BUY/HOLD), confidence scores, regime, sentiment, and top SHAP features."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_stock_rankings",
        "description": (
            "Get top-N ML-ranked stocks for a sector group from the latest portfolio rankings. "
            "Sector groups: tech_comms, healthcare, financials, cyclicals, defensives."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector_group": {
                    "type": "string",
                    "description": "Sector group to query",
                    "enum": list(SECTOR_GROUPS.keys()),
                },
                "top_n": {
                    "type": "integer",
                    "description": "Max stocks to return (default 10)",
                    "default": 10,
                },
            },
            "required": ["sector_group"],
        },
    },
    {
        "name": "get_macro_indicators",
        "description": (
            "Get the latest macro economic indicators from FRED: Fed funds rate, USD/EUR, "
            "USD/JPY, 10y-2y yield spread, breakeven inflation, VIX, CPI YoY, WTI spot, gold fix."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_price_history",
        "description": "Get recent daily closing prices for any commodity or stock ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol (e.g. CL=F, AAPL)"},
                "days": {
                    "type": "integer",
                    "description": "Number of calendar days of history (default 30)",
                    "default": 30,
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sentiment_scores",
        "description": (
            "Get recent FinBERT-based news sentiment scores (last 14 days) for given tickers. "
            "Returns score_1d, score_3d, momentum, and news volume."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols to get sentiment for",
                },
            },
            "required": ["tickers"],
        },
    },
]


@dataclass
class ToolContext:
    session: AsyncSession
    top_n: int = 10


async def _web_search(query: str, max_results: int = 5) -> list[dict]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return [
            {
                "title": "Live search unavailable",
                "content": "TAVILY_API_KEY not configured. Analysis based on database signals only.",
            }
        ]
    try:
        from tavily import TavilyClient  # type: ignore[import]

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = await asyncio.to_thread(
            client.search, query, max_results=max_results, search_depth="advanced"
        )
        results = response.get("results", [])
        return [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": (r.get("content") or "")[:600],
                "published_date": r.get("published_date"),
            }
            for r in results
        ]
    except Exception as exc:
        logger.warning("Tavily search failed for %r: %s", query, exc)
        return [{"title": "Search error", "content": str(exc)}]


async def _get_commodity_signals() -> list[dict]:
    data = await cache_load_json(REDIS_SIGNAL_FILTERED_KEY)
    if not data:
        return []
    return [
        {
            "ticker": s.get("ticker"),
            "name": s.get("name"),
            "signal": s.get("signal"),
            "avg_confidence": s.get("avg_confidence"),
            "confidence_5d": s.get("confidence_5d"),
            "confidence_21d": s.get("confidence_21d"),
            "regime_label": s.get("regime_label"),
            "regime_confidence": s.get("regime_confidence"),
            "sentiment_label": (s.get("sentiment") or {}).get("label"),
            "sentiment_score_1d": (s.get("sentiment") or {}).get("score_1d"),
            "position_size_pct": s.get("position_size_pct"),
            "top_shap_features": [f["feature"] for f in (s.get("shap_features") or [])[:5]],
        }
        for s in data
    ]


async def _get_stock_rankings(sector_group: str, top_n: int, session: AsyncSession) -> list[dict]:
    sectors = SECTOR_GROUPS.get(sector_group, [])
    if not sectors:
        return [{"error": f"Unknown sector_group: {sector_group!r}. Valid: {list(SECTOR_GROUPS)}"}]
    latest_date_row = await session.execute(select(func.max(PortfolioRanking.date)))
    latest_date = latest_date_row.scalar()
    if latest_date is None:
        return [{"note": "No portfolio rankings in database yet. Run stock refresh + retrain first."}]
    rows = await session.execute(
        select(PortfolioRanking)
        .where(PortfolioRanking.date == latest_date, PortfolioRanking.sector.in_(sectors))
        .order_by(PortfolioRanking.rank.asc())
        .limit(top_n)
    )
    return [
        {
            "ticker": r.ticker,
            "score": float(r.score),
            "rank": r.rank,
            "sector": r.sector,
            "in_topk": r.in_topk,
            "as_of": str(r.date),
        }
        for r in rows.scalars().all()
    ]


async def _get_macro_indicators(session: AsyncSession) -> dict:
    row = await session.execute(select(MacroIndicator).order_by(desc(MacroIndicator.date)).limit(1))
    m = row.scalars().first()
    if m is None:
        return {"note": "No macro data in database yet."}

    def f(v: Any) -> float | None:
        return float(v) if v is not None else None

    return {
        "as_of": str(m.date),
        "fed_funds_rate": f(m.fed_funds_rate),
        "usd_eur": f(m.usd_eur),
        "usd_jpy": f(m.usd_jpy),
        "yield_spread_10y2y": f(m.yield_spread_10y2y),
        "breakeven_inflation": f(m.breakeven_inflation),
        "vix": f(m.vix),
        "cpi_yoy": f(m.cpi_yoy),
        "wti_spot": f(m.wti_spot),
        "gold_fix": f(m.gold_fix),
    }


async def _get_price_history(ticker: str, days: int, session: AsyncSession) -> list[dict]:
    cutoff = date.today() - timedelta(days=days)
    rows = await session.execute(
        select(CommodityPrice)
        .where(CommodityPrice.ticker == ticker, CommodityPrice.date >= cutoff)
        .order_by(CommodityPrice.date.asc())
    )
    prices = rows.scalars().all()
    if not prices:
        rows = await session.execute(
            select(StockPrice)
            .where(StockPrice.ticker == ticker, StockPrice.date >= cutoff)
            .order_by(StockPrice.date.asc())
        )
        prices = rows.scalars().all()
    return [{"date": str(p.date), "close": float(p.close) if p.close else None} for p in prices]


async def _get_sentiment_scores(tickers: list[str], session: AsyncSession) -> list[dict]:
    if not tickers:
        return []
    cutoff = date.today() - timedelta(days=14)
    rows = await session.execute(
        select(SentimentScore)
        .where(SentimentScore.ticker.in_(tickers), SentimentScore.date >= cutoff)
        .order_by(SentimentScore.ticker, desc(SentimentScore.date))
    )
    seen: set[str] = set()
    result = []
    for s in rows.scalars().all():
        if s.ticker not in seen:
            seen.add(s.ticker)
            result.append(
                {
                    "ticker": s.ticker,
                    "date": str(s.date),
                    "score_1d": float(s.score_1d) if s.score_1d is not None else None,
                    "score_3d": float(s.score_3d) if s.score_3d is not None else None,
                    "momentum": float(s.momentum) if s.momentum is not None else None,
                    "news_volume": s.volume,
                }
            )
    return result


async def execute_tool(name: str, inputs: dict, ctx: ToolContext) -> Any:
    if name == "web_search":
        return await _web_search(inputs.get("query", ""), inputs.get("max_results", 5))
    if name == "get_commodity_signals":
        return await _get_commodity_signals()
    if name == "get_stock_rankings":
        return await _get_stock_rankings(
            inputs.get("sector_group", ""), inputs.get("top_n", ctx.top_n), ctx.session
        )
    if name == "get_macro_indicators":
        return await _get_macro_indicators(ctx.session)
    if name == "get_price_history":
        return await _get_price_history(inputs.get("ticker", ""), inputs.get("days", 30), ctx.session)
    if name == "get_sentiment_scores":
        return await _get_sentiment_scores(inputs.get("tickers", []), ctx.session)
    return {"error": f"Unknown tool: {name}"}
