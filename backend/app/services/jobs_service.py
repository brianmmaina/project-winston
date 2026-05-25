"""Lifecycle helpers for the ``job_status`` table.

The table already exists from migration ``001_initial`` (job_id PK, name, state,
message, created_at, updated_at). This module gives the API + background tasks a
single place to write/read state so the frontend can poll a job to completion.

State machine:
    pending → running → completed
                      → failed
                      → cancelled (manual, not used yet)

Usage from a background task::

    job_id = await start_job("stock_refresh")
    try:
        ...do work, optionally call ``update_job_progress(job_id, "step 2/3")``...
        await complete_job(job_id, message="rows=12345 batches=11")
    except Exception as exc:  # noqa: BLE001
        await fail_job(job_id, str(exc))
        raise
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobStatus
from app.db.session import async_session_factory

LOGGER = logging.getLogger(__name__)

_TERMINAL_STATES = {"completed", "failed", "cancelled"}


async def _commit(session: AsyncSession) -> None:
    await session.commit()


async def start_job(name: str, *, session: AsyncSession | None = None) -> str:
    """Insert a fresh ``pending`` row and return its ``job_id``.

    If a session is passed, uses it (and the caller is responsible for the txn).
    Otherwise opens its own session/commit.
    """
    job_id = str(uuid.uuid4())
    payload = {"job_id": job_id, "name": name, "state": "pending"}
    if session is not None:
        await session.execute(pg_insert(JobStatus).values(payload))
    else:
        async with async_session_factory() as own:
            await own.execute(pg_insert(JobStatus).values(payload))
            await _commit(own)
    return job_id


async def _set_state(
    job_id: str,
    state: str,
    message: str | None = None,
    *,
    session: AsyncSession | None = None,
) -> None:
    stmt = update(JobStatus).where(JobStatus.job_id == job_id).values(
        state=state,
        message=message,
    )
    if session is not None:
        await session.execute(stmt)
        await _commit(session)
    else:
        async with async_session_factory() as own:
            await own.execute(stmt)
            await _commit(own)


async def mark_running(job_id: str, message: str | None = None) -> None:
    await _set_state(job_id, "running", message)


async def update_job_progress(job_id: str, message: str) -> None:
    """Cheap progress ping (state stays ``running``)."""
    await _set_state(job_id, "running", message)


async def complete_job(job_id: str, message: str | None = None) -> None:
    await _set_state(job_id, "completed", message)


async def fail_job(job_id: str, message: str | None = None) -> None:
    await _set_state(job_id, "failed", message)


async def get_job(job_id: str, *, session: AsyncSession) -> dict[str, Any] | None:
    res = await session.execute(select(JobStatus).where(JobStatus.job_id == job_id).limit(1))
    row = res.scalars().first()
    if row is None:
        return None
    return _serialize(row)


async def recent_jobs(*, session: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    res = await session.execute(
        select(JobStatus).order_by(desc(JobStatus.created_at)).limit(limit)
    )
    return [_serialize(r) for r in res.scalars().all()]


def _serialize(row: JobStatus) -> dict[str, Any]:
    return {
        "job_id": row.job_id,
        "name": row.name,
        "state": row.state,
        "message": row.message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "is_terminal": row.state in _TERMINAL_STATES,
    }


def is_terminal(state: str) -> bool:
    return state in _TERMINAL_STATES


# ---------------------------------------------------------------------------
# Decorator-style wrapper for background tasks.
# ---------------------------------------------------------------------------


async def run_tracked_job(name: str, coro_factory) -> str:
    """Helper that opens a fresh session, calls ``coro_factory(job_id)`` to do
    the work, and updates job_status accordingly. Designed to be called from a
    FastAPI ``BackgroundTasks.add_task`` wrapper.

    ``coro_factory`` is an async callable taking ``job_id`` and returning the
    completion ``message`` string (or ``None``).
    """
    job_id = await start_job(name)
    await mark_running(job_id, "started")
    try:
        msg = await coro_factory(job_id)
        await complete_job(job_id, msg)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Job %s (%s) failed", job_id, name)
        await fail_job(job_id, str(exc)[:512])
        raise
    return job_id
