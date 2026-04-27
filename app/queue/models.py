"""Submit queue model — Tier 1 job submission queue.

One row per analysis-job submission attempt. Lifecycle:

    pending -> running -> done | failed
                       (or)  -> cancelled (only from pending)

The ``inputs_json`` mirrors ``AnalysisRunRequest`` so the worker can
re-construct the call. ``job_id`` is populated when the run starts
(or after, depending on which side wins the race — see
``queue/worker.py``).

Idempotency / crash safety: on boot, ``queue.service.reset_stuck_on_boot``
flips any ``running`` row back to ``pending`` so the worker re-picks it.
The downstream ``analysis_jobs`` row is independent (its own UUID), so
re-running a recovered queue item only risks producing a duplicate
analysis_job — never data corruption.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SubmitQueueItem(Base):
    __tablename__ = "submit_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    inputs_json: Mapped[dict] = mapped_column(JSON(), nullable=False)
    # 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    # 'manual' | 'schedule' | 'fallback'
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="manual"
    )

    enqueued_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    __table_args__ = (
        Index("ix_queue_pending", "status", "enqueued_at"),
        Index("ix_queue_recent", "enqueued_at"),
    )
