"""Generic /v1/admin/loops endpoints — list, fire, abort, cadence.

Phase 4 of the cost-aware iteration. The Processes + Cadences tabs in
the new Admin shell consume these.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.admin import loops as _loops_meta
from app.admin import runtime as _runtime
from app.admin import service as _svc
from app.core.auth import verify_api_key


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class LoopRow(BaseModel):
    loop_id: str
    title: str
    description: str
    default_cadence_seconds: int
    cadence_seconds: int
    supports_abort: bool
    confirm_modal_required: bool
    cost_sensitive: bool
    enabled: bool
    running: bool
    fire_supported: bool
    last_tick_at: Optional[str] = None
    last_tick_ok: Optional[bool] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    last_duration_ms: Optional[int] = None
    fire_cooldown_remaining_seconds: float = 0.0


class LoopsListResponse(BaseModel):
    items: list[LoopRow]
    count: int


class CadenceUpdate(BaseModel):
    cadence_seconds: int = Field(ge=1, le=30 * 24 * 60 * 60)
    enabled: Optional[bool] = None


class SettingsResponse(BaseModel):
    items: dict[str, Any]


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


async def _resolve_cadence(loop_id: str, default_cadence: int) -> int:
    cad = await _svc.get_setting(f"loop.cadence.{loop_id}", default_cadence)
    try:
        return int(cad)
    except (TypeError, ValueError):
        return default_cadence


async def _resolve_enabled(loop_id: str, default_enabled: bool) -> bool:
    val = await _svc.get_setting(f"loop.enabled.{loop_id}", default_enabled)
    return bool(val)


@router.get("/loops", response_model=LoopsListResponse)
async def list_loops(_api_key: str = Depends(verify_api_key)) -> LoopsListResponse:
    rows: list[LoopRow] = []
    statuses = {s.loop_id: s for s in await _svc.list_status()}
    handles = _runtime.all_handles()
    for loop_id, meta in _loops_meta.LOOPS.items():
        cadence = await _resolve_cadence(loop_id, meta.default_cadence_seconds)
        enabled = await _resolve_enabled(loop_id, meta.default_enabled)
        s = statuses.get(loop_id)
        h = handles.get(loop_id)
        running = bool(h and h.task and not h.task.done())
        cooldown = (
            _runtime.fire_debounce_remaining(h) if h is not None else 0.0
        )
        rows.append(
            LoopRow(
                loop_id=loop_id,
                title=meta.title,
                description=meta.description,
                default_cadence_seconds=meta.default_cadence_seconds,
                cadence_seconds=cadence,
                supports_abort=meta.supports_abort,
                confirm_modal_required=meta.confirm_modal_required,
                cost_sensitive=meta.cost_sensitive,
                enabled=enabled,
                running=running,
                fire_supported=bool(h and h.fire_now is not None),
                last_tick_at=_iso(getattr(s, "last_tick_at", None)),
                last_tick_ok=getattr(s, "last_tick_ok", None),
                last_error=getattr(s, "last_error", None),
                last_error_at=_iso(getattr(s, "last_error_at", None)),
                last_duration_ms=getattr(s, "last_duration_ms", None),
                fire_cooldown_remaining_seconds=cooldown,
            )
        )
    return LoopsListResponse(items=rows, count=len(rows))


@router.post("/loops/{loop_id}/fire")
async def fire_loop(
    loop_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    if loop_id not in _loops_meta.LOOPS:
        raise HTTPException(404, f"unknown loop_id: {loop_id}")
    h = _runtime.get(loop_id)
    if h is None or h.fire_now is None:
        raise HTTPException(
            400, f"manual fire not supported for {loop_id} (no handle registered)"
        )
    remaining = _runtime.fire_debounce_remaining(h)
    if remaining > 0:
        raise HTTPException(
            429,
            detail={
                "error": "rate_limited",
                "retry_after_seconds": round(remaining, 2),
            },
        )
    _runtime.stamp_fire(h)
    # Spawn the fire as a background task so the HTTP response is immediate.
    asyncio.create_task(h.fire_now())  # noqa: RUF006 — fire-and-forget by design
    return {"ok": True, "loop_id": loop_id}


@router.post("/loops/{loop_id}/abort")
async def abort_loop(
    loop_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    meta = _loops_meta.LOOPS.get(loop_id)
    if meta is None:
        raise HTTPException(404, f"unknown loop_id: {loop_id}")
    if not meta.supports_abort:
        raise HTTPException(400, f"{loop_id} does not support abort")
    h = _runtime.get(loop_id)
    if h is None or h.stop_event is None:
        raise HTTPException(
            400, f"no live handle for {loop_id} (loop may not be running on this instance)"
        )
    h.stop_event.set()
    if h.task is not None:
        h.task.cancel()
    return {"ok": True, "loop_id": loop_id}


@router.put("/loops/{loop_id}/cadence")
async def update_cadence(
    loop_id: str,
    payload: CadenceUpdate,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    if loop_id not in _loops_meta.LOOPS:
        raise HTTPException(404, f"unknown loop_id: {loop_id}")
    await _svc.set_setting(f"loop.cadence.{loop_id}", payload.cadence_seconds)
    if payload.enabled is not None:
        await _svc.set_setting(f"loop.enabled.{loop_id}", bool(payload.enabled))
    return {
        "ok": True,
        "loop_id": loop_id,
        "cadence_seconds": payload.cadence_seconds,
        "enabled": payload.enabled,
    }


# Settings endpoints — used by the kill-switch toggle in Costs/Cadences tabs.
@router.get("/settings", response_model=SettingsResponse)
async def list_settings(_api_key: str = Depends(verify_api_key)) -> SettingsResponse:
    keys = [
        "anthropic.enabled",
        "anthropic.monthly_cap_usd",
        "tv_context.vision_enabled_this_month",
        "research_weekly.enabled",
        "research_weekly.scope",
        "research_weekly.dedupe_days",
        "research_weekly.max_per_tick",
    ]
    items: dict[str, Any] = {}
    for k in keys:
        items[k] = await _svc.get_setting(k)
    items["anthropic.month_to_date_usd"] = await _svc.month_to_date_anthropic_spend_usd()
    items["anthropic.kill_switch_active"] = await _svc.anthropic_kill_switch_active()
    return SettingsResponse(items=items)


class SettingPut(BaseModel):
    value: Any


@router.put("/settings/{key}")
async def set_setting_endpoint(
    key: str,
    payload: SettingPut,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    # Restrict to a known whitelist so the operator can't write arbitrary
    # keys via the UI.
    allowed = {
        "anthropic.enabled",
        "anthropic.monthly_cap_usd",
        "tv_context.vision_enabled_this_month",
        "research_weekly.enabled",
        "research_weekly.scope",
        "research_weekly.dedupe_days",
        "research_weekly.max_per_tick",
    }
    allowed_prefixes = ("loop.cadence.", "loop.enabled.", "retention.")
    if key not in allowed and not key.startswith(allowed_prefixes):
        raise HTTPException(400, f"setting key not editable: {key}")
    await _svc.set_setting(key, payload.value)
    return {"ok": True, "key": key, "value": payload.value}


# -----------------------------------------------------------------------------
# Costs (Phase 5).
# -----------------------------------------------------------------------------


@router.get("/costs/monthly")
async def costs_monthly(
    month: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    from app.admin import costs as _costs

    return await _costs.monthly_breakdown(month=month)


@router.get("/costs/recent")
async def costs_recent(
    days: int = 30,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    from app.admin import costs as _costs

    if days < 1 or days > 90:
        raise HTTPException(400, "days must be in [1, 90]")
    series = await _costs.daily_series(days=days)
    return {"items": series, "count": len(series)}


@router.get("/costs/top-queries")
async def costs_top_queries(
    limit: int = 10,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    from app.admin import costs as _costs

    if limit < 1 or limit > 50:
        raise HTTPException(400, "limit must be in [1, 50]")
    items = await _costs.top_queries_by_cost(limit=limit)
    return {"items": items, "count": len(items)}


# -----------------------------------------------------------------------------
# Retention (Phase 5).
# -----------------------------------------------------------------------------


@router.get("/retention")
async def retention_status(_api_key: str = Depends(verify_api_key)) -> dict:
    from app.admin import retention as _ret

    items = await _ret.list_class_status()
    return {"items": items, "count": len(items)}


class PurgeRequest(BaseModel):
    confirm: bool = False


@router.post("/retention/{key}/purge")
async def retention_purge(
    key: str,
    payload: PurgeRequest,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Manual purge for one data class. Two-step (preview → confirm).

    Cap = 5000 rows per call so the DB lock window stays bounded. The
    operator can fire repeatedly to drain in batches.
    """
    from app.admin import retention as _ret

    funcs = {
        "prediction_accuracy": _ret.sweep_prediction_accuracy,
        "drift_alerts": _ret.sweep_drift_alerts,
        "research_queries": _ret.sweep_research_queries,
    }
    fn = funcs.get(key)
    if fn is None:
        raise HTTPException(400, f"unknown retention key: {key}")

    if not payload.confirm:
        # Preview: return what *would* be deleted but actually delete nothing.
        # Implemented as a count query in each sweep — for simplicity we just
        # return the cap so the UI can show "up to 5000 will be purged".
        return {
            "preview": True,
            "key": key,
            "cap": _ret.MANUAL_PURGE_CAP,
        }

    deleted = await fn(cap=_ret.MANUAL_PURGE_CAP)
    return {"deleted": deleted, "cap_reached": deleted >= _ret.MANUAL_PURGE_CAP}
