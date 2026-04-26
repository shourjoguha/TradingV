"""Scheduler runner — single asyncio task started in the lifespan.

Loop:
  1. Load config. If disabled, sleep until poll_interval and re-check.
  2. If `is_due(cfg)` → run a tick.
  3. Sleep until ``min(next_run_at, retry_minutes-from-now if pending,
     poll_interval)`` whichever is sooner. The ``_wake`` event lets external
     callers (e.g. analysis service's completion-trigger) cut the sleep short.

Tick:
  - Skip if today is a weekend AND skip_weekends. Advance next_run_at.
  - Skip if watchlist empty. Advance next_run_at.
  - Else call submit_run(...) inline. On 429 (AtCapacityError) → set
    pending_run=true, status=deferred_429. On success → status=succeeded.
    On other exception → status=failed.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional

from app.schedule import service as schedule_svc
from app.watchlist import service as watchlist_svc

logger = logging.getLogger(__name__)

# How often the loop wakes when nothing is scheduled imminently.
# Bounds the staleness when config changes via PUT (worst case operator
# waits this long for an enable to take effect).
_IDLE_POLL_SECONDS = 30

# External wake-up event. analysis.service flips this when a manual job
# completes so a 429-deferred scheduled run can fire immediately.
_wake_event: Optional[asyncio.Event] = None
_run_task: Optional[asyncio.Task] = None


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _collect_actuals(symbols: list[str], intervals: list[str]) -> dict[str, int]:
    """Best-effort OHLCV refresh for every (watchlist symbol × interval).

    Each refresh is independently try/excepted so one provider hiccup on
    a symbol doesn't poison the whole run. Returns a status counter for
    logging visibility.
    """
    from app.market_data import service as md_service

    stats = {"ok": 0, "failed": 0}
    for sym in symbols:
        for interval in intervals:
            try:
                await md_service.refresh(sym, interval)
                stats["ok"] += 1
            except Exception as e:
                logger.warning(
                    "scheduler: actuals refresh failed for %s/%s: %s", sym, interval, e
                )
                stats["failed"] += 1
    logger.info(
        "scheduler: actuals refreshed (%d ok, %d failed)", stats["ok"], stats["failed"]
    )
    return stats


def request_wake() -> None:
    """Public hook: wake the runner without changing state.

    Safe to call from anywhere (including from a different asyncio task).
    No-op if the runner hasn't started.
    """
    if _wake_event is not None:
        _wake_event.set()


async def _tick() -> None:
    """One scheduler iteration. All exceptions caught + recorded; we
    never let a bad tick crash the loop."""
    cfg = await schedule_svc.get_config()
    if not cfg.enabled:
        return

    now = _now_utc()
    tz = schedule_svc.resolve_tz(cfg.tz_name)
    local_now = now.astimezone(tz)
    next_after_run = schedule_svc.compute_next_run_at(cfg, now=now + datetime.timedelta(minutes=1))

    # Weekend guard.
    if cfg.skip_weekends and local_now.weekday() >= 5 and not cfg.pending_run:
        await schedule_svc.record_run(status="skipped_weekend", advance_to=next_after_run)
        return

    # Watchlist empty guard.
    symbols = await watchlist_svc.list_symbols()
    if not symbols:
        await schedule_svc.record_run(status="skipped_empty", advance_to=next_after_run)
        return

    # Run.
    from app.analysis import concurrency, service as analysis_svc

    try:
        job = await analysis_svc.submit_run(
            tickers=symbols,
            intervals=list(cfg.intervals),
            model_ids=list(cfg.model_ids),
            horizon_bars=cfg.horizon_bars,
        )
        logger.info(
            "scheduler: started job %s with %d task(s)", job.id, job.task_count
        )

        # After predictions land, refresh OHLCV cache so actuals for
        # prior target dates are available to comparison endpoints.
        # Best-effort — log failures, don't fail the scheduled run.
        if cfg.collect_actuals:
            await _collect_actuals(symbols, list(cfg.intervals))

        await schedule_svc.record_run(status="succeeded", advance_to=next_after_run)
    except concurrency.AtCapacityError:
        logger.info("scheduler: deferred (manual job in flight); will retry")
        # Don't advance next_run_at — pending_run + retry_minutes drives retry.
        await schedule_svc.set_pending(True)
        await schedule_svc.record_run(status="deferred_429")
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("scheduler: tick failed")
        await schedule_svc.record_run(
            status="failed",
            error=f"{type(e).__name__}: {e}",
            advance_to=next_after_run,
        )


async def _loop() -> None:
    """Main scheduler loop. Cancelled on app shutdown."""
    global _wake_event
    _wake_event = asyncio.Event()

    # Catch-up on missed run: if next_run_at is in the past at startup, fire.
    cfg = await schedule_svc.ensure_config()
    if cfg.next_run_at is None:
        await schedule_svc.update_config(
            enabled=cfg.enabled
        )  # triggers next_run_at recompute via tz/run-at change path
        cfg = await schedule_svc.get_config()
        # Force initial compute even when no field actually changed.
        from app.schedule.service import compute_next_run_at

        async with __import__("app.core.db", fromlist=["SessionLocal"]).SessionLocal() as session:
            from app.schedule.models import SINGLETON_ID, ScheduleConfig

            row = await session.get(ScheduleConfig, SINGLETON_ID)
            if row is not None and row.next_run_at is None:
                row.next_run_at = compute_next_run_at(row)
                await session.commit()

    while True:
        try:
            cfg = await schedule_svc.get_config()
            if schedule_svc.is_due(cfg):
                await _tick()
                continue  # immediately re-check (next_run_at may now be far away)

            # Compute sleep duration.
            now = _now_utc()
            sleep_seconds = _IDLE_POLL_SECONDS
            if cfg.enabled and cfg.next_run_at is not None:
                until_next = (cfg.next_run_at - now).total_seconds()
                if until_next > 0:
                    sleep_seconds = min(sleep_seconds, until_next)
            if cfg.pending_run:
                sleep_seconds = min(sleep_seconds, cfg.retry_minutes * 60)

            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=max(1, sleep_seconds))
            except asyncio.TimeoutError:
                pass
            finally:
                _wake_event.clear()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover
            logger.exception("scheduler: loop iteration crashed; sleeping briefly")
            await asyncio.sleep(5)


def start() -> None:
    """Start the runner task. Idempotent — safe to call multiple times."""
    global _run_task
    if _run_task is not None and not _run_task.done():
        return
    _run_task = asyncio.create_task(_loop(), name="schedule-runner")


async def stop() -> None:
    """Cancel the runner task. Used from tests + shutdown."""
    global _run_task, _wake_event
    if _run_task is not None:
        _run_task.cancel()
        try:
            await _run_task
        except (asyncio.CancelledError, Exception):
            pass
        _run_task = None
    _wake_event = None
