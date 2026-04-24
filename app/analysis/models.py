from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AnalysisJob(Base):
    """A user-submitted analysis request. Parent of one-or-more tasks."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Lifecycle: pending → running → done. `done` even if tasks have errors.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    inputs_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    submitted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tasks: Mapped[list["AnalysisTask"]] = relationship(
        "AnalysisTask", back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )


class AnalysisTask(Base):
    """One (ticker, interval, model_id) cell of a parent job."""

    __tablename__ = "analysis_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Lifecycle: pending → running → (done | ineligible | error).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Populated on done.
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Populated on ineligible: {"reason": "UNSUPPORTED_INTERVAL", "message": "..."}.
    ineligible_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ineligible_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Populated on error (exception bubbled from adapter).
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job: Mapped[AnalysisJob] = relationship("AnalysisJob", back_populates="tasks")
