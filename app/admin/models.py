"""ORM models for the admin module — app_settings + process_status."""
from __future__ import annotations

import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    """Key/value JSONB store. Cascade order: DB > env > default.

    Keys are dotted, e.g. ``research_weekly.enabled``,
    ``anthropic.monthly_cap_usd``, ``loop.cadence.macro``. The ``value_json``
    column stores arbitrary JSON: bool / int / float / str / dict.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[object] = mapped_column(JSON(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessStatus(Base):
    """One row per registered lifespan loop.

    Updated on every tick boundary by ``service.record_tick``. Drives the
    Processes tab UI. ``last_error`` is truncated to 1000 chars; full
    tracebacks stay in the application log.
    """

    __tablename__ = "process_status"

    loop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_tick_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_tick_ok: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_error_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_duration_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
