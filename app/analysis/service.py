"""Analysis orchestration service.

Flow for `submit_run`:
1. Upsert every submitted ticker into the tickers registry (source="analysis").
2. Expand (tickers × intervals × models) into task rows. `models=None`
   means every registered Kronos model.
3. For each task: run `EligibilityValidator.check(...)` against the CURRENT
   OHLCV cache size. Ineligible → close task immediately with structured
   reason. Eligible → call `adapter.predict(...)` and persist the result.
4. Parent `AnalysisJob.status` → "done" once every task resolves.

v1 runs tasks inline (synchronous in the request handler's async context).
This is fine while the stub adapter is in place; once the real Kronos lands
(Phase 5), move this loop onto an `arq` worker keyed off Redis. The SAME
validator + persistence shape stays — only the dispatch changes.
"""
from __future__ import annotations

import datetime
import logging
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import concurrency
from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.kronos import service as kservice
from app.kronos.adapter import get_adapter
from app.kronos.registry import load_models
from app.kronos.schemas import Eligible, Ineligible
from app.kronos.validator import EligibilityValidator
from app.market_data import service as md_service
from app.market_data.intervals import is_canonical
from app.tickers import service as tickers_svc

logger = logging.getLogger(__name__)


class AnalysisInputError(ValueError):
    """Raised for request-time validation failures (before any task is created)."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _resolve_model_ids(requested: Optional[Iterable[str]]) -> List[str]:
    registered = [m.id for m in load_models()]
    if requested is None:
        return registered
    req_list = list(requested)
    unknown = [m for m in req_list if m not in registered]
    if unknown:
        raise AnalysisInputError(f"unknown model_ids: {unknown}")
    return req_list


async def submit_run(
    *,
    tickers: List[str],
    intervals: List[str],
    model_ids: Optional[List[str]] = None,
    horizon_bars: Optional[int] = None,
) -> AnalysisJob:
    tickers = [t for t in (s.strip() for s in tickers) if t]
    if not tickers:
        raise AnalysisInputError("at least one ticker required")
    bad_intervals = [i for i in intervals if not is_canonical(i)]
    if bad_intervals:
        raise AnalysisInputError(f"unsupported intervals: {bad_intervals}")

    resolved_models = _resolve_model_ids(model_ids)

    inputs = {
        "tickers": [tickers_svc.normalize(t) for t in tickers],
        "intervals": list(intervals),
        "model_ids": resolved_models,
        "horizon_bars": horizon_bars,
    }

    # Acquire the concurrency gate BEFORE any DB writes so we don't leave
    # orphan job rows when another job is already running. Raises
    # AtCapacityError which the route layer surfaces as 429.
    async with concurrency.acquire_slot():
        async with _db.SessionLocal() as session:
            job = AnalysisJob(inputs_json=inputs, status="pending")
            session.add(job)
            await session.flush()

            # Upsert each ticker + build task rows.
            tasks: List[AnalysisTask] = []
            for sym in inputs["tickers"]:
                await tickers_svc.upsert_ticker(session, sym, source="analysis")
                for interval in inputs["intervals"]:
                    for model_id in resolved_models:
                        tasks.append(
                            AnalysisTask(
                                job_id=job.id,
                                ticker=sym,
                                interval=interval,
                                model_id=model_id,
                            )
                        )
            session.add_all(tasks)
            job.task_count = len(tasks)
            await session.commit()
            job_id = job.id

        # Process tasks inline for v1; swap for a worker in Phase 5.
        await _process_job(job_id, horizon_bars=horizon_bars)

    return await get_job(job_id)  # type: ignore[return-value]


async def _process_job(job_id: str, *, horizon_bars: Optional[int]) -> None:
    async with _db.SessionLocal() as session:
        job = await session.get(AnalysisJob, job_id)
        if job is None:
            logger.warning("job %s disappeared before processing", job_id)
            return
        job.status = "running"
        await session.commit()

        result = await session.execute(
            select(AnalysisTask).where(AnalysisTask.job_id == job_id)
        )
        task_ids = [t.id for t in result.scalars().all()]

    for task_id in task_ids:
        await _process_task(task_id, horizon_bars=horizon_bars)

    pairs: list[tuple[str, str]] = []
    async with _db.SessionLocal() as session:
        job = await session.get(AnalysisJob, job_id)
        if job is not None:
            job.status = "done"
            job.finished_at = _now()
            await session.commit()
            ticker_syms = list(set(job.inputs_json.get("tickers", [])))
            for sym in ticker_syms:
                t = await tickers_svc.get_ticker(session, sym)
                asset_class = t.asset_class if t else "unknown"
                pairs.append((sym, asset_class))

    # Fire-and-forget sync to peer backend.
    if pairs:
        import asyncio

        from app.sync import service as sync_service

        if sync_service.peer_configured():
            await sync_service.enqueue(pairs)
            asyncio.create_task(sync_service.drain_outbox())


async def _process_task(task_id: str, *, horizon_bars: Optional[int]) -> None:
    async with _db.SessionLocal() as session:
        task = await session.get(AnalysisTask, task_id)
        if task is None:
            return
        task.status = "running"
        task.started_at = _now()
        await session.commit()

        # Resolve asset class for validation.
        t = await tickers_svc.get_ticker(session, task.ticker)
        if t is None:
            from app.tickers.asset_class import infer_asset_class

            asset_class = infer_asset_class(task.ticker)
        else:
            asset_class = t.asset_class

    available_bars = await md_service.count_cached(task.ticker, task.interval)

    outcome = EligibilityValidator.check(
        model_id=task.model_id,
        asset_class=asset_class,
        interval=task.interval,
        available_bars=available_bars,
        available_features=kservice.CACHE_FEATURES,
        horizon_bars=horizon_bars,
    )

    async with _db.SessionLocal() as session:
        task = await session.get(AnalysisTask, task_id)
        if task is None:
            return
        task.finished_at = _now()

        if isinstance(outcome, Ineligible):
            task.status = "ineligible"
            task.ineligible_reason = outcome.reason.value
            task.ineligible_message = outcome.message
            await session.commit()
            return

        assert isinstance(outcome, Eligible)
        try:
            bars = await md_service.get_cached(
                task.ticker, task.interval, limit=outcome.context_length
            )
            prediction = get_adapter().predict(outcome, bars)
            task.status = "done"
            task.result_json = {
                "model_id": prediction.model_id,
                "horizon_bars": prediction.horizon_bars,
                "forecast": prediction.forecast,
                "meta": prediction.meta,
            }
        except NotImplementedError as e:
            # Stub path (adapter intentionally refuses). Surface cleanly.
            task.status = "error"
            task.error = f"adapter_not_wired: {e}"
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("task %s adapter failed", task_id)
            task.status = "error"
            task.error = f"{type(e).__name__}: {e}"

        await session.commit()


async def get_job(job_id: str) -> Optional[AnalysisJob]:
    async with _db.SessionLocal() as session:
        return await session.get(AnalysisJob, job_id)


async def list_jobs(*, limit: int = 50, offset: int = 0) -> List[AnalysisJob]:
    async with _db.SessionLocal() as session:
        result = await session.execute(
            select(AnalysisJob)
            .order_by(AnalysisJob.submitted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
