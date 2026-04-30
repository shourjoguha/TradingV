"""Schedule config service.

CRUD helpers + pure ``compute_next_run_at`` for the runner. Everything
that touches `schedule_config` goes through here so the singleton-row
invariant is enforced in one place.
"""
from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.schedule.models import SINGLETON_ID, ScheduleConfig

logger = logging.getLogger(__name__)

# Defaults match the locked product spec. v1: enabled=False (operator
# must opt in via PUT /v1/schedule).
_DEFAULTS = dict(
    enabled=False,
    tz_name="UTC",
    run_at_local=datetime.time(23, 30),
    intervals=["1d"],
    horizon_bars=5,
    model_ids=["kronos_base"],
    retry_minutes=5,
    collect_actuals=True,
    skip_weekends=True,
    fallback_offset_hours=6,
    pending_run=False,
)


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def ensure_config() -> ScheduleConfig:
    """Idempotently create the singleton row if missing."""
    async with _db.SessionLocal() as session:
        cfg = await session.get(ScheduleConfig, SINGLETON_ID)
        if cfg is not None:
            return cfg
        cfg = ScheduleConfig(id=SINGLETON_ID, **_DEFAULTS)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
        return cfg


async def get_config() -> ScheduleConfig:
    cfg = await ensure_config()
    # Reload via a fresh session so caller doesn't share with our writer.
    async with _db.SessionLocal() as session:
        result = await session.get(ScheduleConfig, SINGLETON_ID)
        assert result is not None  # ensure_config guaranteed it
        return result


async def update_config(**fields) -> ScheduleConfig:
    """Partial update. Only non-None fields applied. Returns fresh row.

    Enqueues a replication push so the peer backend stays in sync. Skipped
    when called via :func:`apply_imported_config` (which writes directly).
    """
    await ensure_config()
    async with _db.SessionLocal() as session:
        cfg = await session.get(ScheduleConfig, SINGLETON_ID)
        assert cfg is not None
        for k, v in fields.items():
            if v is None:
                continue
            setattr(cfg, k, v)
        # Recompute next_run_at if scheduling-relevant fields changed.
        if any(k in fields for k in ("enabled", "tz_name", "run_at_local")):
            cfg.next_run_at = compute_next_run_at(cfg)
        await session.commit()
        await session.refresh(cfg)

    await _enqueue_replication(cfg)
    return cfg


# ----------------------------------------------------------------------
# Replication
# ----------------------------------------------------------------------

# Fields the peer should NOT clobber on import — these are runtime state
# specific to whichever backend is actually doing the runs.
_LOCAL_ONLY_FIELDS = {
    "pending_run", "last_run_at", "last_run_status", "last_run_error",
    "next_run_at", "id",
}


def _serialize_for_replication(cfg: ScheduleConfig) -> dict:
    """Snapshot of config-only fields (no runtime state) for the peer."""
    return {
        "enabled": cfg.enabled,
        "tz_name": cfg.tz_name,
        "run_at_local": cfg.run_at_local.isoformat() if cfg.run_at_local else None,
        "intervals": list(cfg.intervals or []),
        "horizon_bars": cfg.horizon_bars,
        "model_ids": list(cfg.model_ids or []),
        "retry_minutes": cfg.retry_minutes,
        "collect_actuals": cfg.collect_actuals,
        "skip_weekends": cfg.skip_weekends,
        "fallback_offset_hours": cfg.fallback_offset_hours,
    }


async def _enqueue_replication(cfg: ScheduleConfig) -> None:
    try:
        from app.sync import service as sync_svc

        await sync_svc.enqueue_kind("schedule", _serialize_for_replication(cfg))
    except Exception:  # pragma: no cover - defensive
        logger.exception("schedule: replication enqueue failed")


async def apply_imported_config(payload: dict) -> str:
    """Apply a peer-pushed schedule config. Last-write-wins on shared fields.

    Local-only runtime fields (``pending_run``, ``last_run_*``, ``next_run_at``)
    are preserved — each backend has its own runtime state. Returns
    ``'updated'`` or ``'noop'``.
    """
    import datetime as _dt

    if not isinstance(payload, dict):
        return "noop"
    await ensure_config()
    async with _db.SessionLocal() as session:
        cfg = await session.get(ScheduleConfig, SINGLETON_ID)
        if cfg is None:
            return "noop"

        for key, value in payload.items():
            if key in _LOCAL_ONLY_FIELDS:
                continue
            if value is None:
                continue
            if key == "run_at_local" and isinstance(value, str):
                value = _dt.time.fromisoformat(value)
            setattr(cfg, key, value)

        # Recompute next_run_at locally — it's our timeline, not theirs.
        cfg.next_run_at = compute_next_run_at(cfg)
        await session.commit()
        await session.refresh(cfg)
    return "updated"


async def set_pending(value: bool) -> None:
    """Toggle the pending_run flag. Called by the runner on AtCapacity and
    by the analysis service's completion-trigger hook."""
    await ensure_config()
    async with _db.SessionLocal() as session:
        cfg = await session.get(ScheduleConfig, SINGLETON_ID)
        if cfg is None:
            return
        cfg.pending_run = value
        await session.commit()


async def record_run(
    *,
    status: str,
    error: Optional[str] = None,
    advance_now: Optional[datetime.datetime] = None,
) -> None:
    """Persist last_run_* + (optional) recompute next_run_at.

    When ``advance_now`` is provided, ``next_run_at`` is recomputed *here*
    against the freshly-loaded config — not against a snapshot precomputed
    by the caller. This is the choke point that keeps a mid-tick
    ``PUT /v1/schedule`` from being silently overwritten: the PUT lands
    between tick start and end, ``record_run`` reads the post-PUT row,
    and ``compute_next_run_at`` reflects the operator's new
    ``run_at_local`` / ``tz_name`` / ``enabled`` / ``skip_weekends``.
    """
    await ensure_config()
    async with _db.SessionLocal() as session:
        cfg = await session.get(ScheduleConfig, SINGLETON_ID)
        if cfg is None:
            return
        cfg.last_run_at = _now_utc()
        cfg.last_run_status = status
        cfg.last_run_error = error
        if advance_now is not None:
            cfg.next_run_at = compute_next_run_at(cfg, now=advance_now)
        if status == "succeeded":
            cfg.pending_run = False
        await session.commit()


# ----------------------------------------------------------------------
# Pure helpers (no DB) — exported so they can be unit-tested in isolation.
# ----------------------------------------------------------------------

def resolve_tz(tz_name: str) -> datetime.tzinfo:
    """Return tzinfo for ``tz_name``, falling back to UTC on bad input."""
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        logger.warning("schedule: unknown tz '%s', defaulting to UTC", tz_name)
        return datetime.timezone.utc


def compute_next_run_at(
    cfg: ScheduleConfig, *, now: Optional[datetime.datetime] = None
) -> datetime.datetime:
    """Compute the next UTC datetime the schedule should fire.

    Logic:
    - Convert ``now`` into ``cfg.tz_name``.
    - Build today's run instant from ``cfg.run_at_local``.
    - If still in the future, return that (in UTC).
    - Else advance by 1 day.
    - If ``cfg.skip_weekends``, advance further to next weekday.
    """
    if now is None:
        now = _now_utc()
    tz = resolve_tz(cfg.tz_name)
    local_now = now.astimezone(tz)

    candidate = local_now.replace(
        hour=cfg.run_at_local.hour,
        minute=cfg.run_at_local.minute,
        second=cfg.run_at_local.second,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate = candidate + datetime.timedelta(days=1)

    if cfg.skip_weekends:
        # weekday(): Mon=0..Sun=6. Push past Sat/Sun to Monday.
        while candidate.weekday() >= 5:
            candidate = candidate + datetime.timedelta(days=1)

    return candidate.astimezone(datetime.timezone.utc)


def is_due(
    cfg: ScheduleConfig, *, now: Optional[datetime.datetime] = None
) -> bool:
    """True iff scheduler should fire NOW (enabled, watchlist non-empty
    check happens in the runner — this is just the time predicate).

    Considers `pending_run` to allow completion-trigger / 429-retry to fire
    out-of-band.
    """
    if not cfg.enabled:
        return False
    if cfg.pending_run:
        return True
    if cfg.next_run_at is None:
        return False
    if now is None:
        now = _now_utc()
    return now >= cfg.next_run_at
