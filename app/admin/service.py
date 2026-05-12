"""Admin service — settings cascade, process_status writes, cost guards.

The cascade order for any setting is **DB > env > hardcoded default**. The
DB row wins; env-var seeds first boot only. ``get_setting`` is the single
entry point for code that reads a configurable knob.
"""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core import db as _db
from app.admin.models import AppSetting, ProcessStatus


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Settings cascade — DB > env > default.
# -----------------------------------------------------------------------------

# Hardcoded defaults that don't have a Pydantic Settings entry. These cover
# the cost-aware guards introduced in Phase 4 + a few admin-UI knobs.
_HARDCODED_DEFAULTS: dict[str, Any] = {
    "anthropic.enabled": True,
    "anthropic.monthly_cap_usd": 5.0,
    "tv_context.vision_enabled_this_month": True,
    "research_weekly.enabled": False,         # cost-aware C1
    "research_weekly.scope": "at_risk",       # cost-aware C2
    "research_weekly.dedupe_days": 30,        # don't re-stress same hyp within N days
    "research_weekly.max_per_tick": 3,        # backlog cap per tick
}


def _coerce_env(env_value: str, default: Any) -> Any:
    """Best-effort cast of an env-var string to the default's type."""
    if isinstance(default, bool):
        return env_value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(env_value)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(env_value)
        except ValueError:
            return default
    return env_value


async def get_setting(key: str, default: Any = None) -> Any:
    """Read a settings value with cascade: DB > env > hardcoded > caller default.

    Idempotent and cheap (single PK fetch). No caching — admin changes must
    take effect on the next read.
    """
    # 1) DB row wins.
    async with _db.SessionLocal() as session:
        row = await session.get(AppSetting, key)
        if row is not None:
            return row.value_json

    # 2) Env var.
    env_key = key.upper().replace(".", "_")
    if env_key in os.environ:
        seed = _HARDCODED_DEFAULTS.get(key, default)
        return _coerce_env(os.environ[env_key], seed)

    # 3) Hardcoded default.
    if key in _HARDCODED_DEFAULTS:
        return _HARDCODED_DEFAULTS[key]

    # 4) Caller-provided default (may be None).
    return default


async def set_setting(key: str, value: Any) -> None:
    """Upsert a setting. JSON-serializable values only."""
    async with _db.SessionLocal() as session:
        bind = session.bind or session.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        now = datetime.datetime.now(datetime.timezone.utc)
        if dialect == "postgresql":
            stmt = pg_insert(AppSetting).values(
                key=key, value_json=value, updated_at=now
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[AppSetting.key],
                set_={"value_json": value, "updated_at": now},
            )
            await session.execute(stmt)
        elif dialect == "sqlite":
            stmt = sqlite_insert(AppSetting).values(
                key=key, value_json=value, updated_at=now
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[AppSetting.key],
                set_={"value_json": value, "updated_at": now},
            )
            await session.execute(stmt)
        else:
            existing = await session.get(AppSetting, key)
            if existing is None:
                session.add(
                    AppSetting(key=key, value_json=value, updated_at=now)
                )
            else:
                existing.value_json = value
                existing.updated_at = now
        await session.commit()


# -----------------------------------------------------------------------------
# Process status — recorded by every loop on tick boundaries.
# -----------------------------------------------------------------------------

_MAX_ERR_LEN = 1000


async def record_tick(
    loop_id: str,
    *,
    ok: bool,
    duration_ms: int,
    error: Optional[str] = None,
) -> None:
    """Write a single tick result into ``process_status``. Never raises.

    Called by the lifespan loops directly (no decorator) so existing
    bespoke control flow stays intact.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        async with _db.SessionLocal() as session:
            row = await session.get(ProcessStatus, loop_id)
            err_truncated = (
                error[:_MAX_ERR_LEN] if error else None
            )
            if row is None:
                row = ProcessStatus(
                    loop_id=loop_id,
                    last_tick_at=now,
                    last_tick_ok=ok,
                    last_error=err_truncated,
                    last_error_at=now if not ok else None,
                    last_duration_ms=duration_ms,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.last_tick_at = now
                row.last_tick_ok = ok
                if not ok:
                    row.last_error = err_truncated
                    row.last_error_at = now
                row.last_duration_ms = duration_ms
                row.updated_at = now
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("record_tick(%s) failed: %s", loop_id, e)


async def get_status(loop_id: str) -> Optional[ProcessStatus]:
    async with _db.SessionLocal() as session:
        return await session.get(ProcessStatus, loop_id)


async def list_status() -> list[ProcessStatus]:
    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(ProcessStatus))).scalars().all()
    return list(rows)


# -----------------------------------------------------------------------------
# Cost guards (C3 + C4).
# -----------------------------------------------------------------------------


async def anthropic_kill_switch_active() -> bool:
    """True when calls to the Anthropic API should refuse.

    Two paths flip this: explicit operator toggle and automatic monthly-cap
    enforcement. The two settings are independent — either alone trips it.
    """
    enabled = await get_setting("anthropic.enabled", True)
    if not bool(enabled):
        return True
    cap = await get_setting("anthropic.monthly_cap_usd", 5.0)
    if cap is None or cap <= 0:
        return False
    spend = await month_to_date_anthropic_spend_usd()
    return spend >= float(cap)


async def month_to_date_anthropic_spend_usd() -> float:
    """Sum est_cost_usd across research_queries + tv_context vision in this month.

    Imported lazily so a cold ``app.admin`` module doesn't drag in tv_context
    + research models.
    """
    from app.research.models import ResearchQuery
    from app.tv_context.models import TVContextItem

    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with _db.SessionLocal() as session:
        rq_rows = (
            await session.execute(
                select(ResearchQuery.est_cost_usd).where(
                    ResearchQuery.asked_at >= month_start
                )
            )
        ).scalars().all()
        rq_total = float(sum(c for c in rq_rows if c is not None))

        tv_rows = (
            await session.execute(
                select(TVContextItem.payload).where(
                    TVContextItem.captured_at >= month_start,
                    TVContextItem.kind == "screenshot",
                )
            )
        ).scalars().all()
        tv_total = 0.0
        for payload in tv_rows:
            if not payload:
                continue
            cost = (
                payload.get("vision", {}).get("cost_usd")
                if isinstance(payload, dict)
                else None
            )
            if cost is not None:
                try:
                    tv_total += float(cost)
                except (TypeError, ValueError):
                    pass
    return rq_total + tv_total
