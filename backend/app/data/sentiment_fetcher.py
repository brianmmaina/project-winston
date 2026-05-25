"""RSS headlines + FinBERT scoring -> sentiment_scores."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COMMODITIES, COMMODITY_KEYWORDS, RSS_FEEDS
from app.core.config import get_settings
from app.db.models import SentimentScore
from app.db.operations import upsert_sentiment
from app.ml.finbert_nlp import get_finbert, score_single_with_pipe

logger = logging.getLogger(__name__)


def _match_tickers(text: str) -> list[str]:
    lower = text.lower()
    hit: list[str] = []
    for ticker, kws in COMMODITY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in lower:
                hit.append(ticker)
                break
    return hit


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
            except Exception:
                dt = None
        out.append({"text": text, "published": dt})
    return out


def _aggregate_rows_for_date(
    as_of: date,
    ticker_to_scores: dict[str, list[float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in COMMODITIES:
        scores = ticker_to_scores.get(ticker, [])
        if not scores:
            score_1d = 0.0
            vol = 0
        else:
            score_1d = float(sum(scores) / len(scores))
            vol = int(len(scores))

        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "score_1d": score_1d,
                "score_3d": None,
                "volume": vol,
                "momentum": None,
            }
        )
    return rows


def _apply_rolling_from_history(
    today_rows: list[dict[str, Any]],
    history: dict[str, pd.Series],
) -> list[dict[str, Any]]:
    """history maps ticker -> Series indexed by date of score_1d (last 5 days)."""
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


async def load_recent_sentiment_history(session: AsyncSession, days: int = 5) -> dict[str, pd.Series]:
    end = date.today()
    start = end - timedelta(days=days + 3)
    res = await session.execute(
        select(SentimentScore.ticker, SentimentScore.date, SentimentScore.score_1d).where(
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


async def ingest_sentiment(session: AsyncSession) -> int:
    """Pull RSS feeds, score with FinBERT, upsert aggregates for NYC 'today'."""
    settings = get_settings()
    timeout = float(settings.sentiment_rss_timeout_s)

    tz = ZoneInfo(settings.timezone)
    as_of_ny = datetime.now(tz).date()

    ticker_scores: defaultdict[str, list[float]] = defaultdict(list)
    headlines_scored = 0

    pipe = await asyncio.to_thread(get_finbert)

    for _, url in RSS_FEEDS.items():
        try:
            body = await _fetch_feed(url, timeout)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RSS fetch failed (%s): %s", url, exc)
            continue

        entries = _parse_entries(body)
        texts: list[str] = []
        meta: list[list[str]] = []
        for e in entries:
            tix = _match_tickers(e["text"])
            if not tix:
                continue
            texts.append(e["text"])
            meta.append(tix)

        if not texts:
            continue

        for text, tickers_line in zip(texts, meta, strict=False):
            scores_dict = await asyncio.to_thread(score_single_with_pipe, pipe, text)
            composite = float(scores_dict["composite"])
            for tkr in set(tickers_line):
                ticker_scores[tkr].append(composite)
            headlines_scored += 1

    history = await load_recent_sentiment_history(session)
    rows = _aggregate_rows_for_date(as_of_ny, dict(ticker_scores))
    merged = _apply_rolling_from_history(rows, history)

    await upsert_sentiment(session, merged)
    await session.commit()

    logger.info("ingest_sentiment tickers_hit=%s headlines=%s date=%s", len(ticker_scores), headlines_scored, as_of_ny)
    return headlines_scored
