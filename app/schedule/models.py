"""Daily forecast scheduler config (singleton row, id=1).

The runner (``app/schedule/runner.py``) reads this row, computes
``next_run_at``, sleeps until then, fires a ``submit_run`` over every
watchlist symbol × ``intervals`` × ``model_ids`` for ``horizon_bars`` ahead.
"""
from __future__ import annotations

import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# The single config row's primary key. Anywhere we touch this table we
# upsert/update id=SINGLETON_ID.
SINGLETON_ID = 1


class ScheduleConfig(Base):
    __tablename__ = "schedule_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.coalesce(False, False)
    )
    # IANA tz name (e.g. "America/New_York", "Europe/London"). Default UTC.
    tz_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    run_at_local: Mapped[datetime.time] = mapped_column(Time(), nullable=False)
    intervals: Mapped[list] = mapped_column(JSON, nullable=False)
    horizon_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    model_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    retry_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    collect_actuals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    skip_weekends: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Railway-fallback inference (only used on Railway; harmless on laptop).
    # If no `origin='peer'` job lands by run_at_local + fallback_offset_hours,
    # Railway runs the models itself against its own watchlist. Per-ticker
    # dedupe via `prediction_points`. Disabled by default — flip
    # ``RAILWAY_FALLBACK_ENABLED=true`` env on Railway to opt in.
    fallback_offset_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default="6"
    )

    # Set when a scheduled run hits AtCapacityError (429); the runner
    # retries every retry_minutes until cleared. Also set on
    # completion-trigger from analysis service (so the scheduler fires
    # immediately when an in-flight manual job ends).
    pending_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # succeeded | deferred_429 | skipped_weekend | skipped_empty
    # | skipped_disabled | failed
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
