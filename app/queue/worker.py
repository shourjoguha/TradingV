"""Single-flight queue worker — Tier 1.

One coroutine wrapped in the lifespan task. Drains ``submit_queue`` FIFO
by calling the existing ``analysis.service.submit_run`` for each pending
item. Worker is single-flight by design (one in-flight job per backend);
the existing concurrency gate inside ``submit_run`` stays as belt-and-
braces (see [tech_debt.md](../../.claude/tech_debt.md)).

Wake-up: ``request_wake()`` from anywhere (route, scheduler) cuts the
poll sleep short so newly-enqueued items start immediately.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core import db as _db
from app.queue import service as _qsvc

logger = logging.getLogger(__name__)

# Fallback poll cadence when nothing wakes us. 5s is short enough that a
# misfire doesn't add user-visible latency, long enough to be cheap.
_POLL_SECONDS = 5

_wake_event: Optional[asyncio.Event] = None


def request_wake() -> None:
    """Wake the worker now. Safe to call from any task; no-op before start."""
    global _wake_event
    if _wake_event is not None:
        try:
            _wake_event.set()
        except RuntimeError:
            # Event from a different loop — shouldn't happen but stay quiet.
            pass


async def _process_one(queue_id: str, inputs: dict) -> None:
    """Run one queued submission via the existing analysis pipeline."""
    from app.analysis import service as _asvc
    from app.analysis.concurrency import AtCapacityError

    try:
        job = await _asvc.submit_run(
            tickers=inputs.get("tickers", []),
            intervals=inputs.get("intervals", []),
            model_ids=inputs.get("model_ids"),
            horizon_bars=inputs.get("horizon_bars", 0),
        )
        await _qsvc.mark_done(queue_id, job_id=job.id)
    except AtCapacityError as e:
        # Should never happen under single-worker discipline, but the slot
        # gate is still in place. Mark failed; operator can re-enqueue.
        logger.error(
            "queue.worker: AtCapacityError on %s — slot gate fired despite single-flight queue",
            queue_id,
        )
        await _qsvc.mark_failed(queue_id, error=f"at_capacity: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("queue.worker: submit_run failed for %s", queue_id)
        await _qsvc.mark_failed(queue_id, error=f"{type(e).__name__}: {e}")


async def worker_loop(*, stop_event: Optional[asyncio.Event] = None) -> None:
    """Long-lived task. Drains queue serially; sleeps until next wake.

    Lifecycle:
    - Try to claim oldest pending. If found → run, then loop without
      sleeping (drain back-to-back).
    - If empty → wait on _wake_event with _POLL_SECONDS timeout, then retry.
    - On stop_event set → exit cleanly.
    """
    global _wake_event
    _wake_event = asyncio.Event()
    logger.info("queue.worker_loop started")

    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("queue.worker_loop stopping (signal)")
            return

        # Claim phase — own session so the row lock doesn't bleed across
        # the long-running process_one call.
        claimed_id: Optional[str] = None
        claimed_inputs: Optional[dict] = None
        try:
            async with _db.SessionLocal() as session:
                item = await _qsvc.claim_next(session)
                if item is not None:
                    claimed_id = item.id
                    claimed_inputs = item.inputs_json
                    await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("queue.worker: claim_next failed: %s", e)
            # Back off briefly so we don't busy-loop on a broken DB.
            await asyncio.sleep(1.0)
            continue

        if claimed_id is None:
            # Queue empty — wait for wake or poll timeout.
            _wake_event.clear()
            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
            continue

        # Run phase — outside the claim transaction.
        try:
            await _process_one(claimed_id, claimed_inputs or {})
        except asyncio.CancelledError:
            # Process was killed mid-job. Reset stuck row so a future
            # boot picks it up via reset_stuck_on_boot().
            raise
