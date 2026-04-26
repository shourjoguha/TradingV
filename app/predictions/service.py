"""Materialise ``analysis_tasks.result_json.forecast[]`` into flat rows.

Two entry points:
- :func:`explode_task` — called from analysis service when a task transitions
  to ``done``. Inserts rows for that single task.
- :func:`backfill_all` — one-shot CLI/route to regenerate the table from
  every existing done task. Idempotent: skips tasks that already have rows.

The JSON forecast schema (from ``RealKronosAdapter.predict``) is::

    forecast: [
      {ts: "<iso>", open, high, low, close, volume, amount},
      ...
    ]
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.predictions.models import PredictionPoint

logger = logging.getLogger(__name__)


def _parse_iso(s: str | None) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def _ensure_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _derive_made_on(
    task: AnalysisTask | dict, job_submitted_at: datetime.datetime | None = None
) -> datetime.date:
    """``made_on`` = UTC date of when the forecast was actually computed.

    Prefer ``task.started_at``. Fall back to job's ``submitted_at`` (used
    for imported snapshots that may not include task started_at).
    """
    started: Any
    if isinstance(task, dict):
        started = _parse_iso(task.get("started_at")) or _parse_iso(task.get("finished_at"))
    else:
        started = task.started_at or task.finished_at
    if started is None:
        started = job_submitted_at
    if started is None:
        started = datetime.datetime.now(datetime.timezone.utc)
    return _ensure_utc(started).date()


def _build_rows_from_forecast(
    *,
    task_id: str,
    ticker: str,
    model_id: str,
    interval: str,
    made_on: datetime.date,
    forecast: list[dict],
) -> list[PredictionPoint]:
    rows: list[PredictionPoint] = []
    for offset, bar in enumerate(forecast or [], start=1):
        ts = _parse_iso(bar.get("ts"))
        if ts is None:
            logger.warning("prediction_points: skipping bar with bad ts in task %s", task_id)
            continue
        ts = _ensure_utc(ts)
        rows.append(
            PredictionPoint(
                task_id=task_id,
                ticker=ticker,
                model_id=model_id,
                interval=interval,
                made_on=made_on,
                made_on_dow=made_on.weekday(),
                target_date=ts.date(),
                target_ts=ts,
                horizon_offset=offset,
                open=float(bar.get("open", 0.0)),
                high=float(bar.get("high", 0.0)),
                low=float(bar.get("low", 0.0)),
                close=float(bar.get("close", 0.0)),
                volume=float(bar["volume"]) if bar.get("volume") is not None else None,
                amount=float(bar["amount"]) if bar.get("amount") is not None else None,
            )
        )
    return rows


async def _replace_rows_for_task(
    session: AsyncSession, *, task_id: str, rows: list[PredictionPoint]
) -> int:
    """Idempotent insert: clear any existing rows for the task, insert fresh.
    Returns count inserted."""
    await session.execute(delete(PredictionPoint).where(PredictionPoint.task_id == task_id))
    if rows:
        session.add_all(rows)
    return len(rows)


async def explode_task(task_id: str) -> int:
    """Read one task + materialise its forecast list. Returns rows inserted.

    No-op (returns 0) if the task is missing, not ``done``, or has no
    forecast data.
    """
    async with _db.SessionLocal() as session:
        task = await session.get(AnalysisTask, task_id)
        if task is None or task.status != "done":
            return 0
        result = task.result_json or {}
        forecast = result.get("forecast") or []
        if not forecast:
            return 0

        job = await session.get(AnalysisJob, task.job_id)
        made_on = _derive_made_on(task, job.submitted_at if job else None)

        rows = _build_rows_from_forecast(
            task_id=task.id,
            ticker=task.ticker,
            model_id=task.model_id,
            interval=task.interval,
            made_on=made_on,
            forecast=forecast,
        )
        n = await _replace_rows_for_task(session, task_id=task.id, rows=rows)
        await session.commit()
        return n


async def explode_imported_tasks(payload: dict) -> int:
    """Re-derive prediction_points from a peer-imported job snapshot.

    Called from ``analysis.service.import_job`` after the job + tasks are
    inserted. Handles dict-shaped tasks (from JSON payload) without
    needing to round-trip through SQLAlchemy.
    """
    job_blob = payload.get("job") or {}
    submitted = _parse_iso(job_blob.get("submitted_at"))
    inserted = 0
    async with _db.SessionLocal() as session:
        for t in payload.get("tasks") or []:
            if t.get("status") != "done":
                continue
            forecast = (t.get("result_json") or {}).get("forecast") or []
            if not forecast:
                continue
            made_on = _derive_made_on(t, submitted)
            rows = _build_rows_from_forecast(
                task_id=t["id"],
                ticker=t.get("ticker", ""),
                model_id=t.get("model_id", ""),
                interval=t.get("interval", ""),
                made_on=made_on,
                forecast=forecast,
            )
            inserted += await _replace_rows_for_task(session, task_id=t["id"], rows=rows)
        await session.commit()
    return inserted


async def backfill_all(
    *, since: Optional[datetime.date] = None, only_missing: bool = True
) -> dict[str, int]:
    """Regenerate the prediction_points table from analysis_tasks history.

    - ``since``: only consider tasks whose started_at >= this date.
    - ``only_missing``: skip tasks that already have rows (default).
      Set False to fully rewrite (e.g. after a forecast-format change).

    Returns ``{"scanned": n, "exploded": n, "rows_inserted": n, "skipped": n}``.
    """
    stats = {"scanned": 0, "exploded": 0, "rows_inserted": 0, "skipped": 0}
    async with _db.SessionLocal() as session:
        stmt = select(AnalysisTask).where(AnalysisTask.status == "done")
        if since is not None:
            stmt = stmt.where(AnalysisTask.started_at >= since)
        result = await session.execute(stmt)
        tasks = list(result.scalars().all())
        stats["scanned"] = len(tasks)

        for task in tasks:
            forecast = (task.result_json or {}).get("forecast") or []
            if not forecast:
                stats["skipped"] += 1
                continue

            if only_missing:
                exists = await session.scalar(
                    select(PredictionPoint.id)
                    .where(PredictionPoint.task_id == task.id)
                    .limit(1)
                )
                if exists is not None:
                    stats["skipped"] += 1
                    continue

            job = await session.get(AnalysisJob, task.job_id)
            made_on = _derive_made_on(task, job.submitted_at if job else None)

            rows = _build_rows_from_forecast(
                task_id=task.id,
                ticker=task.ticker,
                model_id=task.model_id,
                interval=task.interval,
                made_on=made_on,
                forecast=forecast,
            )
            n = await _replace_rows_for_task(session, task_id=task.id, rows=rows)
            stats["exploded"] += 1
            stats["rows_inserted"] += n

        await session.commit()
    return stats
