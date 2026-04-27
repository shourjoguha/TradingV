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

from app.core import db as _db
from app.core.config import SETTINGS
from app.schedule import service as schedule_svc
from app.watchlist import service as watchlist_svc

logger = logging.getLogger(__name__)

# How often the loop wakes when nothing is scheduled imminently.
# Bounds the staleness when config changes via PUT (worst case operator
# waits this long for an enable to take effect).
_IDLE_POLL_SECONDS = 30

# Fallback loop check cadence. We don't need sub-minute precision —
# the deadline math is in hours.
_FALLBACK_POLL_SECONDS = 30 * 60  # 30 min

# External wake-up event. analysis.service flips this when a manual job
# completes so a 429-deferred scheduled run can fire immediately.
_wake_event: Optional[asyncio.Event] = None
_run_task: Optional[asyncio.Task] = None
_fallback_task: Optional[asyncio.Task] = None


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

    # Watchlist empty guard.
    symbols = await watchlist_svc.list_symbols()
    if not symbols:
        await schedule_svc.record_run(status="skipped_empty", advance_to=next_after_run)
        return

    # Per-asset-class trading-day filter. Lets a crypto ticker run on
    # weekends while skipping stocks. Replaces the old single-flag
    # ``skip_weekends`` guard — but ``cfg.skip_weekends=False`` still
    # bypasses the filter entirely (operator override).
    if cfg.skip_weekends and not cfg.pending_run:
        from app.market_data.calendar import is_trading_day
        from app.tickers import service as tickers_svc

        eligible: list[str] = []
        async with _db.SessionLocal() as session:
            for sym in symbols:
                t = await tickers_svc.get_ticker(session, sym)
                ac = t.asset_class if t else None
                if is_trading_day(ac, local_now.date()):
                    eligible.append(sym)

        if not eligible:
            await schedule_svc.record_run(
                status="skipped_weekend", advance_to=next_after_run
            )
            return
        symbols = eligible

    # Run via the queue. The worker drains FIFO; we don't wait for the
    # actual job to finish here — only that the enqueue succeeded. The
    # 'succeeded' status below means "successfully queued for execution".
    from app.queue import service as queue_svc

    try:
        item = await queue_svc.enqueue(
            inputs={
                "tickers": symbols,
                "intervals": list(cfg.intervals),
                "model_ids": list(cfg.model_ids),
                "horizon_bars": cfg.horizon_bars,
            },
            source="schedule",
        )
        logger.info(
            "scheduler: enqueued queue_id=%s (worker will drain)", item["id"]
        )

        # After predictions land, refresh OHLCV cache so actuals for
        # prior target dates are available to comparison endpoints.
        # Best-effort — log failures, don't fail the scheduled run.
        # Note: this runs immediately after enqueue, not after the worker
        # finishes — actuals refresh is independent of job completion.
        if cfg.collect_actuals:
            await _collect_actuals(symbols, list(cfg.intervals))

        await schedule_svc.record_run(status="succeeded", advance_to=next_after_run)
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
    """Start the runner task(s). Idempotent — safe to call multiple times."""
    global _run_task, _fallback_task
    if _run_task is None or _run_task.done():
        _run_task = asyncio.create_task(_loop(), name="schedule-runner")

    # Railway-fallback loop: only on Railway (or any backend with the
    # explicit env opt-in). Skipped on laptop by default since the laptop
    # IS the source of truth.
    if (
        SETTINGS.RAILWAY_FALLBACK_ENABLED
        and SETTINGS.INSTANCE_NAME == "railway"
        and (_fallback_task is None or _fallback_task.done())
    ):
        _fallback_task = asyncio.create_task(
            _fallback_loop(), name="schedule-fallback"
        )


async def stop() -> None:
    """Cancel the runner task(s). Used from tests + shutdown."""
    global _run_task, _fallback_task, _wake_event
    for task_ref in (_run_task, _fallback_task):
        if task_ref is not None:
            task_ref.cancel()
            try:
                await task_ref
            except (asyncio.CancelledError, Exception):
                pass
    _run_task = None
    _fallback_task = None
    _wake_event = None


# ----------------------------------------------------------------------
# Fallback loop (Railway only)
# ----------------------------------------------------------------------

async def _fallback_loop() -> None:
    """Periodic check: if laptop hasn't pushed today's predictions by the
    configured deadline, run them locally on Railway.

    Loop runs every _FALLBACK_POLL_SECONDS. Each iteration:
    1. Load config. If disabled, sleep + retry.
    2. Compute deadline = today's run_at_local (in cfg.tz_name) + fallback_offset_hours, in UTC.
    3. If now < deadline → sleep + retry.
    4. List watchlist symbols.
    5. For each symbol, check if a prediction made TODAY (any model, any
       origin) already exists in prediction_points. If yes → skip. If no
       → include in fallback fire list.
    6. If list non-empty → submit_run(symbols=list, ...).
    """
    logger.info("scheduler: fallback loop starting (Railway opt-in)")
    while True:
        try:
            await _fallback_tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            logger.exception("scheduler: fallback tick crashed; sleeping")
        try:
            await asyncio.sleep(_FALLBACK_POLL_SECONDS)
        except asyncio.CancelledError:
            raise


async def _fallback_tick() -> None:
    """One iteration of the fallback loop. Public-ish for tests."""
    from app.predictions.models import PredictionPoint
    from app.queue import service as queue_svc
    from sqlalchemy import select

    cfg = await schedule_svc.get_config()
    if not cfg.enabled:
        return

    now = _now_utc()
    tz = schedule_svc.resolve_tz(cfg.tz_name)
    local_now = now.astimezone(tz)
    today_local = local_now.date()

    # Most-recent-past instance of run_at_local. If today's run-time is
    # still in the future (e.g. now=12:00, run_at_local=23:30), step back
    # to yesterday's run instance — that's the one whose predictions we
    # were waiting for.
    candidate_local = datetime.datetime.combine(
        today_local, cfg.run_at_local
    ).replace(tzinfo=tz)
    if candidate_local > local_now:
        candidate_local -= datetime.timedelta(days=1)

    deadline_local = candidate_local + datetime.timedelta(
        hours=cfg.fallback_offset_hours
    )
    deadline_utc = deadline_local.astimezone(datetime.timezone.utc)

    if now < deadline_utc:
        return  # Still within the laptop's window.

    symbols = await watchlist_svc.list_symbols()
    if not symbols:
        return

    # Dedupe horizon: skip a ticker if it has any prediction made on or
    # after the candidate run instance's UTC date. Catches both
    # laptop-pushed (origin='peer') and our own prior fallback runs.
    dedupe_made_on = candidate_local.astimezone(datetime.timezone.utc).date()

    # Per-symbol dedupe: skip any symbol that already has a prediction
    # row made today (regardless of which backend produced it).
    from app.core import db as _db

    fire_for: list[str] = []
    async with _db.SessionLocal() as session:
        for sym in symbols:
            existing = await session.scalar(
                select(PredictionPoint.id)
                .where(PredictionPoint.ticker == sym)
                .where(PredictionPoint.made_on >= dedupe_made_on)
                .limit(1)
            )
            if existing is None:
                fire_for.append(sym)

    if not fire_for:
        logger.info("fallback: all watchlist symbols have today's forecast — skipping")
        return

    logger.info(
        "fallback: deadline passed, %d/%d symbols missing — firing local run",
        len(fire_for), len(symbols),
    )
    try:
        item = await queue_svc.enqueue(
            inputs={
                "tickers": fire_for,
                "intervals": list(cfg.intervals),
                "model_ids": list(cfg.model_ids),
                "horizon_bars": cfg.horizon_bars,
            },
            source="fallback",
        )
        logger.info("fallback: enqueued queue_id=%s for %d symbol(s)", item["id"], len(fire_for))
    except Exception:  # pragma: no cover - defensive
        logger.exception("fallback: enqueue failed")
