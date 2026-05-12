"""Helpers for registering loops with the runtime + recording tick status.

Imported by ``app.main:lifespan``. Keep it small — most behaviour lives in
``service`` (DB) and ``runtime`` (in-process state).
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from app.admin import loops as _loops_meta
from app.admin import runtime as _runtime
from app.admin import service as _svc


logger = logging.getLogger(__name__)


def register_handle(
    loop_id: str,
    *,
    stop_event: Optional[asyncio.Event] = None,
    task: Optional[asyncio.Task] = None,
    fire_now: Optional[Callable[[], Awaitable[None]]] = None,
    enabled: bool = True,
) -> None:
    """Register a live handle so /v1/admin/loops/{id}/{fire,abort} can find it."""
    if loop_id not in _loops_meta.LOOPS:
        logger.warning(
            "register_handle: unknown loop_id %s (not in loops registry)",
            loop_id,
        )
    _runtime.register(
        _runtime.LoopHandle(
            loop_id=loop_id,
            stop_event=stop_event,
            task=task,
            fire_now=fire_now,
            enabled=enabled,
        )
    )


@asynccontextmanager
async def tick_status(loop_id: str):
    """Async context manager that records a single tick's outcome.

    Usage::

        async with tick_status("macro"):
            await macro_service.refresh_all()

    Catches and re-raises so the loop's existing error handling stays
    intact. ``record_tick`` itself is best-effort and never raises.
    """
    start = time.perf_counter()
    err: Optional[str] = None
    ok = True
    try:
        yield
    except asyncio.CancelledError:
        # Cancellation isn't an error condition; record but don't suppress.
        ok = False
        err = "cancelled"
        raise
    except BaseException as e:  # noqa: BLE001 — record everything
        ok = False
        err = repr(e)[:1000]
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            await _svc.record_tick(
                loop_id, ok=ok, duration_ms=duration_ms, error=err
            )
        except Exception as e2:  # noqa: BLE001
            logger.debug("tick_status: record_tick swallow %s", e2)


async def assert_registry_drift() -> list[str]:
    """At startup, verify every registered handle is in the static registry.

    Returns the list of mismatches (live but unregistered loop_ids). Empty
    list means all good. The caller logs a warning + writes synthetic
    process_status entries so the operator sees the drift in the UI.
    """
    handles = _runtime.all_handles()
    return [lid for lid in handles if lid not in _loops_meta.LOOPS]
