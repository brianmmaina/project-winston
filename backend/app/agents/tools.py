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
    {
        "name": "get_fundamentals",
        "description": (
            "Get key fundamental data for a stock ticker via yfinance: P/E (trailing and forward), "
            "EV/EBITDA, PEG ratio, profit/operating margins, revenue growth YoY, earnings growth YoY, "
            "beta, 52-week range, current price, market cap. Use for valuation context on any stock pick."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL, NVDA)"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_earnings_calendar",
        "description": (
            "Get the next earnings date for a ticker and historical beat/miss rate over last 8 quarters. "
            "Use to identify upcoming catalyst events and assess track record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_estimate_revisions",
        "description": (
            "Get analyst upgrade/downgrade activity for a ticker over the last 90 days. "
            "Returns upgrade count, downgrade count, and revision trend direction. "
            "Persistent upgrade momentum is one of the strongest stock selection signals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_options_context",
        "description": (
            "Get options market context for a ticker: ATM implied volatility, 30-day historical volatility, "
            "IV/HV ratio (proxy for whether a catalyst is already priced in), and put/call volume ratio. "
            "IV/HV > 1.3 means expensive options (catalyst priced in). IV/HV < 0.8 means cheap options (not priced in)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_insider_activity",
        "description": (
            "Get recent insider transaction activity for a ticker over the last 90 days. "
            "Returns buy/sell counts and net sentiment. Cluster buying by insiders is a strong bullish signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
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


async def _get_fundamentals(ticker: str) -> dict:
    import yfinance as yf

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        info = t.info or {}
        mcap = info.get("marketCap")
        return {
            "ticker": ticker,
            "name": info.get("longName"),
            "sector": info.get("sector"),
            "market_cap_b": round(mcap / 1e9, 2) if mcap else None,
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "peg_ratio": info.get("pegRatio"),
            "profit_margin_pct": round(info["profitMargins"] * 100, 1) if info.get("profitMargins") else None,
            "operating_margin_pct": round(info["operatingMargins"] * 100, 1) if info.get("operatingMargins") else None,
            "revenue_growth_yoy_pct": round(info["revenueGrowth"] * 100, 1) if info.get("revenueGrowth") else None,
            "earnings_growth_yoy_pct": round(info["earningsGrowth"] * 100, 1) if info.get("earningsGrowth") else None,
            "beta": info.get("beta"),
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "pct_from_52w_high": (
                round((info["currentPrice"] / info["fiftyTwoWeekHigh"] - 1) * 100, 1)
                if info.get("currentPrice") and info.get("fiftyTwoWeekHigh")
                else None
            ),
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("get_fundamentals failed for %s: %s", ticker, exc)
        return {"error": str(exc), "ticker": ticker}


async def _get_earnings_calendar(ticker: str) -> dict:
    import yfinance as yf

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        # next earnings date
        next_date = None
        try:
            cal = t.calendar
            if cal is not None and not cal.empty and "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"]
                next_date = str(val.iloc[0])[:10] if hasattr(val, "iloc") else str(val)[:10]
        except Exception:
            pass

        # historical beat rate
        beat, total = 0, 0
        try:
            hist = t.earnings_history
            if hist is not None and not hist.empty:
                for _, row in hist.iterrows():
                    est = row.get("epsEstimate")
                    act = row.get("epsActual")
                    if est is not None and act is not None and est != 0:
                        total += 1
                        if act > est:
                            beat += 1
        except Exception:
            pass

        days_until = None
        if next_date:
            try:
                from datetime import date as date_type
                nd = date_type.fromisoformat(next_date)
                days_until = (nd - date_type.today()).days
            except Exception:
                pass

        return {
            "ticker": ticker,
            "next_earnings_date": next_date,
            "days_until_earnings": days_until,
            "historical_beat_rate": round(beat / total, 2) if total > 0 else None,
            "quarters_analyzed": total,
            "is_earnings_within_4w": days_until is not None and 0 <= days_until <= 28,
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("get_earnings_calendar failed for %s: %s", ticker, exc)
        return {"error": str(exc), "ticker": ticker}


async def _get_estimate_revisions(ticker: str) -> dict:
    import yfinance as yf
    from datetime import datetime as dt, timedelta

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        try:
            upgrades = t.upgrades_downgrades
        except Exception:
            upgrades = None

        if upgrades is None or upgrades.empty:
            return {"ticker": ticker, "upgrades_90d": 0, "downgrades_90d": 0, "revision_trend": "no_data"}

        cutoff = dt.now().astimezone() - timedelta(days=90)
        try:
            if upgrades.index.tz is None:
                upgrades.index = upgrades.index.tz_localize("UTC")
            recent = upgrades[upgrades.index >= cutoff]
        except Exception:
            recent = upgrades.tail(20)

        up_grades = {"Buy", "Strong Buy", "Overweight", "Outperform", "Market Outperform"}
        down_grades = {"Sell", "Strong Sell", "Underperform", "Underweight", "Market Underperform"}

        ups = recent[recent.get("ToGrade", recent.get("Action", "")).isin(up_grades)].shape[0] if not recent.empty else 0
        downs = recent[recent.get("ToGrade", recent.get("Action", "")).isin(down_grades)].shape[0] if not recent.empty else 0

        if ups >= downs * 2 and ups >= 3:
            trend = "strong_upgrade_momentum"
        elif ups > downs:
            trend = "upgrade_momentum"
        elif downs >= ups * 2 and downs >= 3:
            trend = "strong_downgrade_momentum"
        elif downs > ups:
            trend = "downgrade_momentum"
        else:
            trend = "neutral"

        return {
            "ticker": ticker,
            "upgrades_90d": int(ups),
            "downgrades_90d": int(downs),
            "revision_trend": trend,
            "recent_actions": recent[["Firm", "ToGrade"]].head(5).to_dict("records") if not recent.empty else [],
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("get_estimate_revisions failed for %s: %s", ticker, exc)
        return {"error": str(exc), "ticker": ticker}


async def _get_options_context(ticker: str) -> dict:
    import numpy as np
    import yfinance as yf
    from datetime import datetime as dt, timedelta

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        info = t.info or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not current_price:
            return {"ticker": ticker, "error": "no_price"}

        exps = t.options
        if not exps:
            return {"ticker": ticker, "note": "no_options_listed"}

        target = dt.now() + timedelta(days=30)
        best_exp = min(exps, key=lambda x: abs((dt.strptime(x, "%Y-%m-%d") - target).days))

        try:
            chain = t.option_chain(best_exp)
            calls = chain.calls.copy()
            puts = chain.puts.copy()
            calls["dist"] = (calls["strike"] - current_price).abs()
            atm = calls.loc[calls["dist"].idxmin()]
            atm_iv = float(atm["impliedVolatility"]) if atm["impliedVolatility"] > 0 else None
            call_vol = float(calls["volume"].sum())
            put_vol = float(puts["volume"].sum())
            pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else None
        except Exception:
            atm_iv, pc_ratio = None, None

        try:
            hist = t.history(period="60d")
            if not hist.empty and len(hist) > 10:
                rets = hist["Close"].pct_change().dropna()
                hv30 = float(rets.std() * np.sqrt(252))
            else:
                hv30 = None
        except Exception:
            hv30 = None

        iv_hv = round(atm_iv / hv30, 2) if (atm_iv and hv30 and hv30 > 0) else None
        if iv_hv is None:
            assessment = "insufficient_data"
        elif iv_hv > 1.3:
            assessment = "expensive_catalyst_likely_priced_in"
        elif iv_hv < 0.8:
            assessment = "cheap_catalyst_not_priced_in"
        else:
            assessment = "fairly_priced"

        return {
            "ticker": ticker,
            "current_price": current_price,
            "expiration_used": best_exp,
            "atm_iv_pct": round(atm_iv * 100, 1) if atm_iv else None,
            "hv30_pct": round(hv30 * 100, 1) if hv30 else None,
            "iv_hv_ratio": iv_hv,
            "iv_assessment": assessment,
            "put_call_volume_ratio": pc_ratio,
            "interpretation": (
                "IV/HV > 1.3: market already pricing a big move, be cautious. "
                "IV/HV < 0.8: market not pricing a move, good risk/reward if catalyst is real."
            ),
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("get_options_context failed for %s: %s", ticker, exc)
        return {"error": str(exc), "ticker": ticker}


async def _get_insider_activity(ticker: str) -> dict:
    import yfinance as yf

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        try:
            txns = t.insider_transactions
        except Exception:
            txns = None

        if txns is None or txns.empty:
            return {"ticker": ticker, "buys_90d": 0, "sells_90d": 0, "net_sentiment": "no_data"}

        buy_kw = {"Buy", "Purchase", "Automatic Buy"}
        sell_kw = {"Sale", "Sell", "Automatic Sale"}

        txns_reset = txns.reset_index() if txns.index.name else txns
        buys, sells = 0, 0
        recent_list = []
        for _, row in txns_reset.head(20).iterrows():
            txt = str(row.get("Transaction") or row.get("Shares") or "")
            shares = row.get("Shares", 0) or 0
            if any(k.lower() in txt.lower() for k in buy_kw):
                buys += 1
            elif any(k.lower() in txt.lower() for k in sell_kw):
                sells += 1
            insider = row.get("Insider Trading") or row.get("Insider") or ""
            recent_list.append({"insider": str(insider)[:40], "transaction": txt[:30], "shares": int(shares) if shares else None})

        if buys > sells * 2 and buys >= 2:
            net = "strong_insider_buying"
        elif buys > sells:
            net = "net_insider_buying"
        elif sells > buys * 2 and sells >= 2:
            net = "strong_insider_selling"
        elif sells > buys:
            net = "net_insider_selling"
        else:
            net = "neutral"

        return {
            "ticker": ticker,
            "buys_90d": buys,
            "sells_90d": sells,
            "net_sentiment": net,
            "recent_transactions": recent_list[:5],
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("get_insider_activity failed for %s: %s", ticker, exc)
        return {"error": str(exc), "ticker": ticker}


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
    if name == "get_fundamentals":
        return await _get_fundamentals(inputs.get("ticker", ""))
    if name == "get_earnings_calendar":
        return await _get_earnings_calendar(inputs.get("ticker", ""))
    if name == "get_estimate_revisions":
        return await _get_estimate_revisions(inputs.get("ticker", ""))
    if name == "get_options_context":
        return await _get_options_context(inputs.get("ticker", ""))
    if name == "get_insider_activity":
        return await _get_insider_activity(inputs.get("ticker", ""))
    return {"error": f"Unknown tool: {name}"}
