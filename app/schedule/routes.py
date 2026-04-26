from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from app.core.auth import verify_api_key
from app.schedule import runner, service
from app.schedule.schemas import ScheduleConfigRead, ScheduleConfigUpdate

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("", response_model=ScheduleConfigRead)
async def get_schedule(_api_key: str = Depends(verify_api_key)):
    cfg = await service.get_config()
    return ScheduleConfigRead.model_validate(cfg)


@router.put("", response_model=ScheduleConfigRead)
async def update_schedule(
    body: ScheduleConfigUpdate, _api_key: str = Depends(verify_api_key)
):
    # Validate tz_name eagerly so a bad value 400s instead of falling
    # through to UTC silently inside the runner.
    if body.tz_name is not None:
        try:
            service.resolve_tz(body.tz_name)
            import zoneinfo

            zoneinfo.ZoneInfo(body.tz_name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"unknown tz_name: {e}")

    cfg = await service.update_config(**body.model_dump(exclude_unset=True))
    # Wake the runner so config changes take effect immediately.
    runner.request_wake()
    return ScheduleConfigRead.model_validate(cfg)


@router.post("/import", response_model=ScheduleConfigRead)
async def import_schedule(
    payload: Dict[str, Any] = Body(...),
    _api_key: str = Depends(verify_api_key),
):
    """Replication receiver — applies a peer's schedule_config snapshot.

    Last-write-wins on shared fields. Local-only runtime fields
    (``pending_run``, ``last_run_*``, ``next_run_at``) are preserved.
    Bypasses the replication enqueue path to avoid loops.
    """
    await service.apply_imported_config(payload)
    cfg = await service.get_config()
    return ScheduleConfigRead.model_validate(cfg)


@router.post("/fire-now", response_model=ScheduleConfigRead)
async def fire_now(_api_key: str = Depends(verify_api_key)):
    """Force the scheduler to fire on its next loop iteration.

    Useful for ops + frontend "Run now" button. Equivalent to setting
    pending_run=true. Subject to the same MAX_CONCURRENT_JOBS gate.
    """
    await service.set_pending(True)
    runner.request_wake()
    cfg = await service.get_config()
    return ScheduleConfigRead.model_validate(cfg)
