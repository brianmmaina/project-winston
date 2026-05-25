"""Stock-level sentiment from general business RSS feeds.

We don't have per-ticker RSS for 500 stocks, so the strategy is:

1. Pull a handful of high-volume markets/business RSS feeds.
2. For each headline, extract every S&P 500 ticker mentioned by:
   * exact (case-sensitive) ticker / ``$TICKER`` match, OR
   * (case-insensitive) company-name alias match (derived from
     ``InstrumentMetadata.name`` / the ``STOCKS`` constants snapshot).
3. Score each headline once with FinBERT, then attribute that composite score
   to every ticker the headline mentions.
4. Aggregate per (ticker, NYC date) and persist into ``sentiment_scores``.
   Stock tickers and commodity tickers don't collide, so they share the table.

The materializer (``app.ml.features_stocks``) joins the resulting sentiment as
``score_1d``/``score_3d``/``momentum``/``volume`` features into the panel.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants_stocks import STOCKS
from app.core.config import get_settings
from app.db.models import InstrumentMetadata, SentimentScore
from app.db.operations import upsert_sentiment
from app.ml.finbert_nlp import get_finbert, score_single_with_pipe

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


STOCK_RSS_FEEDS: dict[str, str] = {
    "yahoo_top": "https://feeds.finance.yahoo.com/rss/2.0/category-stocks",
    "marketwatch_top": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "marketwatch_realtime": "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/",
    "cnbc_business": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
}


# ---------------------------------------------------------------------------
# Ticker-mention extractor
# ---------------------------------------------------------------------------


# Strip these as suffixes from company names when generating aliases.
_NAME_SUFFIXES = (
    " Inc.",
    " Inc",
    " Incorporated",
    " Corp.",
    " Corp",
    " Corporation",
    " Co.",
    " Co",
    " Company",
    " Companies",
    " Ltd.",
    " Ltd",
    " plc",
    " PLC",
    " S.A.",
    " SA",
    " N.V.",
    " NV",
    " Holdings",
    " Holding",
    " Group",
    " (The)",
    " The",
    " & Co.",
    " & Co",
    " ADR",
    " Class A",
    " Class B",
    " Class C",
)

# Aliases shorter than this (after stripping suffixes) are dropped because they
# would create huge false-positive volume on common English words.
_MIN_ALIAS_LEN = 4

# Hard ban: alias strings that are common English words and trigger false
# positives even if the name is short. Lowercased.
_ALIAS_BLACKLIST = frozenset(
    {
        "target",  # ticker TGT — name "Target" too generic
        "well",
        "match",
        "block",
        "snap",
        "wynn",
        "the",
        "now",
        "live",
        "best",
        "first",
        "second",
        "national",
        "international",
        "global",
        "american",
        "general",
        "advance",
        "host",
        "everest",
        "trade",
        "service",
        "brand",
        "park",
        "vision",
        "rest",
    }
)


def _normalize_alias(alias: str) -> str:
    s = alias.strip()
    s = s.replace("&amp;", "&")
    return s


def _company_aliases(name: str) -> list[str]:
    """Return additional aliases derived from a company name."""
    n = _normalize_alias(name)
    if not n:
        return []

    # Strip suffixes iteratively (e.g. "Apple Inc." → "Apple").
    changed = True
    while changed:
        changed = False
        for suf in _NAME_SUFFIXES:
            if n.lower().endswith(suf.lower()):
                n = n[: -len(suf)].rstrip(", ").strip()
                changed = True
    n = n.strip(",. ")

    aliases: list[str] = []
    if len(n) >= _MIN_ALIAS_LEN and n.lower() not in _ALIAS_BLACKLIST:
        aliases.append(n)

    # Drop trailing "Communications", "Technologies", "Energy" etc. and try the
    # head form as a separate alias (e.g. "Verizon Communications" → "Verizon").
    head_words = n.split()
    if len(head_words) >= 2:
        head = head_words[0]
        if (
            len(head) >= _MIN_ALIAS_LEN
            and head.lower() not in _ALIAS_BLACKLIST
            and head not in aliases
        ):
            aliases.append(head)

    return aliases


@dataclass(frozen=True)
class TickerMatcher:
    ticker: str
    ticker_re: re.Pattern[str]
    name_re: re.Pattern[str] | None

    def find(self, text: str) -> bool:
        if self.ticker_re.search(text):
            return True
        if self.name_re is not None and self.name_re.search(text):
            return True
        return False


def _build_ticker_regex(ticker: str) -> re.Pattern[str]:
    """Case-sensitive regex matching ``TICKER``, ``$TICKER`` (whole-word)."""
    t = re.escape(ticker)
    # \b doesn't always behave well around ``$``; include it in the lookbehind.
    return re.compile(rf"(?:(?<![A-Z0-9])\${t}(?![A-Z0-9]))|(?:\b{t}\b)")


def _build_name_regex(aliases: list[str]) -> re.Pattern[str] | None:
    if not aliases:
        return None
    parts = sorted({a for a in aliases if a}, key=len, reverse=True)
    if not parts:
        return None
    body = "|".join(re.escape(p) for p in parts)
    return re.compile(rf"\b(?:{body})\b", re.IGNORECASE)


def build_matchers(ticker_to_name: dict[str, str]) -> list[TickerMatcher]:
    """Pre-compile per-ticker matchers. Call once per ingest run.

    ``ticker_to_name`` should typically come from the live
    ``InstrumentMetadata`` table (so aliases stay fresh as the universe
    rebalances), with ``STOCKS`` as a fallback.
    """
    out: list[TickerMatcher] = []
    for ticker, name in ticker_to_name.items():
        tre = _build_ticker_regex(ticker)
        aliases = _company_aliases(name) if name else []
        nre = _build_name_regex(aliases)
        out.append(TickerMatcher(ticker=ticker, ticker_re=tre, name_re=nre))
    return out


def match_tickers_in_text(text: str, matchers: list[TickerMatcher]) -> list[str]:
    """Return the (deduplicated, order-preserving) list of tickers mentioned."""
    if not text:
        return []
    hit: list[str] = []
    seen: set[str] = set()
    for m in matchers:
        if m.find(text) and m.ticker not in seen:
            hit.append(m.ticker)
            seen.add(m.ticker)
    return hit


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def _fetch_feed(url: str, timeout: float) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "commodity-advisor/1.0"})
        r.raise_for_status()
        return r.text


def _parse_entries(body: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(body)
    out: list[dict[str, Any]] = []
    for e in parsed.entries or []:
        title = (e.get("title") or "").strip()
        summary = (e.get("summary") or e.get("description") or "").strip()
        text = f"{title}. {summary}".strip()
        if not text:
            continue
        published = e.get("published_parsed") or e.get("updated_parsed")
        dt: datetime | None = None
        if published:
            try:
                dt = datetime(*published[:6], tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                dt = None
        out.append({"text": text, "published": dt})
    return out


async def _resolve_ticker_to_name(session: AsyncSession) -> dict[str, str]:
    """Prefer DB-seeded names (kept fresh by the daily ingest) over the JSON
    snapshot in ``STOCKS``.
    """
    res = await session.execute(
        select(InstrumentMetadata.ticker, InstrumentMetadata.name).where(
            InstrumentMetadata.asset_class == "stock"
        )
    )
    rows = res.all()
    out: dict[str, str] = {str(t): str(n) for t, n in rows if t and n}
    # Fill any holes from the constants snapshot.
    for t, n in STOCKS.items():
        out.setdefault(t, n)
    return out


def _aggregate_today(
    as_of: date,
    ticker_scores: dict[str, list[float]],
) -> list[dict[str, Any]]:
    """One row per ticker that had at least one mention today."""
    rows: list[dict[str, Any]] = []
    for ticker, scores in ticker_scores.items():
        if not scores:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "score_1d": float(sum(scores) / len(scores)),
                "score_3d": None,
                "volume": int(len(scores)),
                "momentum": None,
            }
        )
    return rows


async def _load_recent_history(
    session: AsyncSession, tickers: list[str], days: int = 5
) -> dict[str, pd.Series]:
    if not tickers:
        return {}
    end = date.today()
    start = end - timedelta(days=days + 3)
    res = await session.execute(
        select(SentimentScore.ticker, SentimentScore.date, SentimentScore.score_1d).where(
            SentimentScore.ticker.in_(tickers),
            SentimentScore.date >= start,
            SentimentScore.date < end,
        )
    )
    bucket: dict[str, dict[date, float]] = defaultdict(dict)
    for tkr, d, s1 in res.all():
        if s1 is None:
            continue
        bucket[str(tkr)][d] = float(s1)
    out: dict[str, pd.Series] = {}
    for tkr, m in bucket.items():
        idx = sorted(m.keys())
        out[tkr] = pd.Series({pd.Timestamp(k): m[k] for k in idx})
    return out


def _apply_rolling(
    today_rows: list[dict[str, Any]],
    history: dict[str, pd.Series],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in today_rows:
        t = row["ticker"]
        d = row["date"]
        s1 = float(row["score_1d"] or 0.0)
        series = history.get(t, pd.Series(dtype=float)).copy()
        series.loc[pd.Timestamp(d)] = s1
        series = series.sort_index().tail(5)
        s3 = float(series.rolling(3, min_periods=1).mean().iloc[-1])
        mom = float(s1 - s3)
        out.append(
            {
                "ticker": t,
                "date": d,
                "score_1d": s1,
                "score_3d": s3,
                "volume": int(row["volume"] or 0),
                "momentum": mom,
            }
        )
    return out


async def ingest_stock_sentiment(session: AsyncSession) -> dict[str, Any]:
    """End-to-end ingest. Returns ``{tickers_hit, headlines_scored, date}``."""
    settings = get_settings()
    timeout = float(settings.sentiment_rss_timeout_s)
    tz = ZoneInfo(settings.timezone)
    as_of = datetime.now(tz).date()

    ticker_to_name = await _resolve_ticker_to_name(session)
    matchers = build_matchers(ticker_to_name)

    pipe = await asyncio.to_thread(get_finbert)

    ticker_scores: defaultdict[str, list[float]] = defaultdict(list)
    headlines_scored = 0

    for feed_id, url in STOCK_RSS_FEEDS.items():
        try:
            body = await _fetch_feed(url, timeout)
        except Exception as exc:  # noqa: BLE001
            logger.warning("stock RSS fetch failed (%s, %s): %s", feed_id, url, exc)
            continue

        entries = _parse_entries(body)
        for e in entries:
            tix = match_tickers_in_text(e["text"], matchers)
            if not tix:
                continue
            try:
                scored = await asyncio.to_thread(score_single_with_pipe, pipe, e["text"])
            except Exception:  # noqa: BLE001
                logger.exception("FinBERT scoring failed; skipping headline")
                continue
            composite = float(scored["composite"])
            for t in tix:
                ticker_scores[t].append(composite)
            headlines_scored += 1

    today_rows = _aggregate_today(as_of, dict(ticker_scores))
    history = await _load_recent_history(session, [r["ticker"] for r in today_rows])
    merged = _apply_rolling(today_rows, history)

    if merged:
        await upsert_sentiment(session, merged)
        await session.commit()

    logger.info(
        "ingest_stock_sentiment date=%s tickers_hit=%d headlines=%d",
        as_of,
        len(ticker_scores),
        headlines_scored,
    )
    return {
        "date": as_of.isoformat(),
        "tickers_hit": len(ticker_scores),
        "headlines_scored": headlines_scored,
    }
