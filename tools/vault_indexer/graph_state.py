"""Debounced background scheduling for graph recompute.

The /reload endpoint triggers a recompute, but a burst of /reload calls
(e.g. operator ticks 10 review-queue items in quick succession) shouldn't
trigger 10 separate recomputes. This module provides a single cancellable
asyncio task per process: each ``schedule()`` call cancels any pending
task and starts a new one that fires after a quiet period.

The actual compute runs `graph_compute.recompute(con)` which is fully
synchronous (NetworkX). It's wrapped in `asyncio.to_thread` so the event
loop isn't blocked.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from . import graph_compute as _graph_compute

log = logging.getLogger("vault-indexer.graph_state")

_PENDING: Optional[asyncio.Task] = None


async def _run_after_delay(con, delay_seconds: float) -> dict | None:
    """Sleep, then run recompute. Cancellation during sleep is the no-op
    expected behavior (a newer schedule() superseded this one)."""
    try:
        await asyncio.sleep(delay_seconds)
    except asyncio.CancelledError:
        return None
    try:
        result = await asyncio.to_thread(_graph_compute.recompute, con)
        return result
    except Exception as e:                       # noqa: BLE001
        log.exception("graph recompute crashed: %s", e)
        return {"status": "error", "error": str(e)}


def schedule(con, *, debounce_seconds: float) -> None:
    """Cancel any pending recompute and schedule a new one.

    Safe to call from a sync FastAPI handler — it grabs the running loop
    if any. If no loop is running (e.g. CLI), runs synchronously.
    """
    global _PENDING

    if _PENDING is not None and not _PENDING.done():
        _PENDING.cancel()
        log.debug("cancelled prior pending recompute")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop — run synchronously. Used by CLI / tests.
        log.info("no event loop; running recompute synchronously")
        _graph_compute.recompute(con)
        return

    _PENDING = loop.create_task(_run_after_delay(con, debounce_seconds))
    log.debug("scheduled recompute in %.1fs", debounce_seconds)


def has_pending() -> bool:
    return _PENDING is not None and not _PENDING.done()


async def cancel_pending() -> None:
    """Cancel any pending recompute. Used by tests or graceful shutdown."""
    global _PENDING
    if _PENDING is not None and not _PENDING.done():
        _PENDING.cancel()
        try:
            await _PENDING
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _PENDING = None
