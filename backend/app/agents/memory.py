"""Agent memory service — persist and retrieve past analyses.

Search strategy (layered):
1. sentence-transformers cosine similarity (all-MiniLM-L6-v2, 384-dim).
   Embeddings stored as JSONB.  Gives true semantic retrieval.
2. TF-IDF cosine similarity (sklearn) — fallback when embeddings are absent.
3. PostgreSQL tsvector pre-filter to bound the candidate set.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC
from typing import Any

import numpy as np
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentMemory

logger = logging.getLogger(__name__)


def _build_embed_text(summary: str | None, top_picks: list | None, full_text: str | None) -> str:
    """Compose a representative string to embed for this memory."""
    parts = []
    if summary:
        parts.append(summary)
    if top_picks:
        parts.append("Picks: " + " ".join(top_picks))
    if full_text:
        parts.append(full_text[:600])
    return " ".join(parts)


async def save_agent_memories(run_id: str, sub_results: list, session: AsyncSession) -> None:
    """Persist each sub-agent's analysis to the memory table after a pipeline run."""
    from app.ml.embedding import embed_batch

    records: list[AgentMemory] = []
    embed_inputs: list[str] = []

    for result in sub_results:
        if result.error:
            continue
        parsed = result.parsed or {}
        summary = parsed.get("summary") or result.text[:500]
        top_picks = parsed.get("top_picks", [])
        try:
            mem = AgentMemory(
                run_id=run_id,
                agent_name=result.name,
                created_at=datetime.now(tz=UTC),
                tickers_covered=parsed.get("tickers") or top_picks,
                summary=summary,
                key_findings=parsed.get("key_findings") or parsed.get("findings"),
                top_picks=top_picks,
                risks=parsed.get("risks") or parsed.get("bear_cases"),
                full_text=result.text,
            )
            records.append(mem)
            embed_inputs.append(_build_embed_text(summary, top_picks, result.text))
        except Exception as exc:
            logger.warning("Failed to build memory for %s: %s", result.name, exc)

    # Compute embeddings in a thread so we don't block the event loop
    embeddings: list[list[float]] = []
    if records:
        try:
            embeddings = await asyncio.to_thread(embed_batch, embed_inputs)
        except Exception as exc:
            logger.warning("Embedding generation failed, storing without vectors: %s", exc)
            embeddings = [None] * len(records)  # type: ignore[list-item]

    for mem, emb in zip(records, embeddings):
        mem.embedding_json = emb
        session.add(mem)

    try:
        await session.commit()
    except Exception as exc:
        logger.warning("Memory commit failed: %s", exc)
        await session.rollback()


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D arrays (already normalised → dot product)."""
    return float(np.dot(a, b))


def _vector_rank(
    records: list[AgentMemory], query_vec: np.ndarray, limit: int, agent_name: str | None
) -> list[AgentMemory]:
    """Rank records by embedding cosine similarity; skip those without embeddings."""
    scored: list[tuple[float, AgentMemory]] = []
    for r in records:
        if not r.embedding_json:
            continue
        if agent_name and r.agent_name != agent_name:
            continue
        sim = _cosine_sim(query_vec, np.array(r.embedding_json, dtype=np.float32))
        scored.append((sim, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def _tfidf_search(
    records: list[AgentMemory], query: str, limit: int, agent_name: str | None
) -> list[AgentMemory]:
    """TF-IDF cosine similarity fallback when embeddings are absent."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [f"{r.summary or ''} {(r.full_text or '')[:800]}" for r in records]
    vec = TfidfVectorizer(stop_words="english", max_features=8000, sublinear_tf=True)
    matrix = vec.fit_transform(corpus)
    q_vec = vec.transform([query])
    sims = cosine_similarity(q_vec, matrix).flatten()
    if agent_name:
        mask = np.array([1.0 if r.agent_name == agent_name else 0.0 for r in records])
        sims = sims * mask
    top_idx = np.argsort(sims)[-limit:][::-1]
    return [records[i] for i in top_idx if sims[i] > 1e-6]


def _format(rows: list[AgentMemory]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": r.run_id,
            "agent_name": r.agent_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "summary": r.summary,
            "top_picks": r.top_picks or [],
            "key_findings": r.key_findings,
        }
        for r in rows
    ]


async def search_memory(
    session: AsyncSession, query: str, agent_name: str | None = None, limit: int = 5
) -> list[dict[str, Any]]:
    """Semantic search over past agent analyses.

    Primary path: sentence-transformer embedding cosine similarity.
    Fallback 1: TF-IDF cosine similarity (sklearn).
    Fallback 2: recency order (if both fail).

    A tsvector pre-filter bounds the candidate pool to ≤300 rows so the
    in-Python similarity scan stays sub-millisecond at any realistic scale.
    """
    from app.ml.embedding import embed

    # --- candidate pool (tsvector pre-filter) ---------------------------------
    ts_filter = text(
        "to_tsvector('english', coalesce(full_text, '') || ' ' || coalesce(summary, ''))"
        " @@ plainto_tsquery('english', :q)"
    ).bindparams(q=query)
    try:
        result = await session.execute(
            select(AgentMemory).where(ts_filter).order_by(desc(AgentMemory.created_at)).limit(300)
        )
        candidates = list(result.scalars().all())
    except Exception:
        candidates = []

    if not candidates:
        broad = select(AgentMemory).order_by(desc(AgentMemory.created_at)).limit(300)
        if agent_name:
            broad = broad.where(AgentMemory.agent_name == agent_name)
        result = await session.execute(broad)
        candidates = list(result.scalars().all())

    if not candidates:
        return []

    # --- primary: embedding similarity ----------------------------------------
    has_embeddings = any(r.embedding_json for r in candidates)
    if has_embeddings:
        try:
            query_vec = np.array(
                await asyncio.to_thread(embed, query), dtype=np.float32
            )
            rows = _vector_rank(candidates, query_vec, limit, agent_name)
            if rows:
                return _format(rows)
        except Exception as exc:
            logger.debug("Embedding search failed, falling back to TF-IDF: %s", exc)

    # --- fallback: TF-IDF -----------------------------------------------------
    try:
        return _format(_tfidf_search(candidates, query, limit, agent_name))
    except Exception as exc:
        logger.debug("TF-IDF search failed, returning recency order: %s", exc)
        filtered = [r for r in candidates if not agent_name or r.agent_name == agent_name]
        return _format(filtered[:limit])


async def get_recent_analyses(session: AsyncSession, agent_name: str, limit: int = 3) -> list[dict[str, Any]]:
    """Retrieve the most recent analyses for a specific agent."""
    q = await session.execute(
        select(AgentMemory)
        .where(AgentMemory.agent_name == agent_name)
        .order_by(desc(AgentMemory.created_at))
        .limit(limit)
    )
    rows = q.scalars().all()
    return [
        {
            "run_id": r.run_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "summary": r.summary,
            "top_picks": r.top_picks or [],
            "risks": r.risks or [],
        }
        for r in rows
    ]
