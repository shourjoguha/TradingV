"""Submit-queue service — enqueue, list, get, cancel, recover.

Worker logic lives in ``app/queue/worker.py`` to keep this file readable.

Why separate ``service`` and ``worker``: the route layer + scheduler call
``enqueue`` and never want to import the asyncio loop scaffolding. Tests
also drive the service directly without spinning the worker.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.queue.models import SubmitQueueItem

logger = logging.getLogger(__name__)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _serialize(item: SubmitQueueItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "status": item.status,
        "source": item.source,
        "inputs": item.inputs_json,
        "enqueued_at": item.enqueued_at.isoformat(),
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "job_id": item.job_id,
        "error": item.error,
    }


async def enqueue(
    *, inputs: dict[str, Any], source: str = "manual"
) -> dict[str, Any]:
    """Insert a pending row. Returns the serialized item.

    ``inputs`` should be the validated AnalysisRunRequest payload as a dict
    (route + scheduler call ``model_dump()`` before passing in).
    """
    if source not in ("manual", "schedule", "fallback"):
        raise ValueError(f"invalid source: {source}")

    async with _db.SessionLocal() as session:
        item = SubmitQueueItem(inputs_json=inputs, source=source)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        out = _serialize(item)

    # Wake the worker so it picks this up immediately rather than on the
    # 5s poll. Lazy import to avoid the worker module pulling in service
    # at import time.
    from app.queue import worker as _worker

    _worker.request_wake()
    return out


async def get(queue_id: str) -> Optional[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        item = await session.get(SubmitQueueItem, queue_id)
        return _serialize(item) if item else None


async def list_items(
    *, status: Optional[str] = None, limit: int = 50
) -> list[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        stmt = (
            select(SubmitQueueItem)
            .order_by(SubmitQueueItem.enqueued_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(SubmitQueueItem.status == status)
        rows = (await session.execute(stmt)).scalars().all()
        return [_serialize(r) for r in rows]


async def cancel(queue_id: str) -> tuple[bool, str]:
    """Cancel a pending item.

    Returns ``(success, current_status)``. Only ``pending`` items can be
    cancelled — anything else returns ``(False, current_status)``.
    """
    async with _db.SessionLocal() as session:
        item = await session.get(SubmitQueueItem, queue_id)
        if item is None:
            return False, "not_found"
        if item.status != "pending":
            return False, item.status
        item.status = "cancelled"
        item.finished_at = _now()
        await session.commit()
        return True, "cancelled"


async def claim_next(session: AsyncSession) -> Optional[SubmitQueueItem]:
    """Atomically grab the oldest pending item, mark it running, return it.

    Returns ``None`` when the queue is empty.

    Uses ``FOR UPDATE SKIP LOCKED`` on Postgres for safe concurrent claims;
    falls back to a serial SELECT-then-UPDATE on SQLite (tests). Since we
    only run a single worker per process this race is mostly theoretical,
    but the locking semantics are correct either way.
    """
    dialect = session.bind.dialect.name if session.bind else ""
    if dialect == "postgresql":
        # SKIP LOCKED so contending workers don't queue behind each other.
        # LIMIT 1 then re-fetch under the row lock.
        stmt = (
            select(SubmitQueueItem)
            .where(SubmitQueueItem.status == "pending")
            .order_by(SubmitQueueItem.enqueued_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    else:
        # SQLite path — single-process tests; FIFO via order_by alone.
        stmt = (
            select(SubmitQueueItem)
            .where(SubmitQueueItem.status == "pending")
            .order_by(SubmitQueueItem.enqueued_at.asc())
            .limit(1)
        )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        return None
    item.status = "running"
    item.started_at = _now()
    await session.flush()
    return item


async def mark_done(queue_id: str, *, job_id: Optional[str] = None) -> None:
    async with _db.SessionLocal() as session:
        item = await session.get(SubmitQueueItem, queue_id)
        if item is None:
            return
        item.status = "done"
        item.finished_at = _now()
        if job_id is not None:
            item.job_id = job_id
        await session.commit()


async def mark_failed(queue_id: str, *, error: str) -> None:
    async with _db.SessionLocal() as session:
        item = await session.get(SubmitQueueItem, queue_id)
        if item is None:
            return
        item.status = "failed"
        item.finished_at = _now()
        item.error = error[:65535]
        await session.commit()


async def reset_stuck_on_boot() -> int:
    """Flip any 'running' row back to 'pending'.

    Called once at lifespan startup. Only ever fires when the previous
    process died mid-job. Returns the count of rows reset (0 on a clean
    boot).
    """
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(SubmitQueueItem).where(SubmitQueueItem.status == "running")
            )
        ).scalars().all()
        for r in rows:
            logger.warning(
                "queue.reset_stuck: row %s was 'running' at boot — reverting to 'pending'",
                r.id,
            )
            r.status = "pending"
            r.started_at = None
        await session.commit()
        return len(rows)


async def queue_stats() -> dict[str, int]:
    """Counts by status — for dashboard widget + observability."""
    out = {"pending": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
    async with _db.SessionLocal() as session:
        from sqlalchemy import func as _func

        stmt = select(SubmitQueueItem.status, _func.count(SubmitQueueItem.id)).group_by(
            SubmitQueueItem.status
        )
        for status, count in (await session.execute(stmt)).all():
            if status in out:
                out[status] = int(count)
    return out
