"""prediction_points explode + backfill + auto-derive on task done / import."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select

from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.predictions import service as predictions_svc
from app.predictions.models import PredictionPoint

HEADERS = {"X-API-Key": "test-key"}


def _forecast_bar(ts_iso: str, **overrides):
    base = {"ts": ts_iso, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
            "volume": 1000.0, "amount": 0.0}
    base.update(overrides)
    return base


async def _seed_done_task(
    *,
    task_id: str = "task-1",
    job_id: str = "job-1",
    ticker: str = "AAPL",
    started_at: datetime.datetime | None = None,
    forecast: list[dict] | None = None,
):
    started_at = started_at or datetime.datetime(2026, 4, 27, 12, 0, tzinfo=datetime.timezone.utc)
    forecast = forecast or [
        _forecast_bar("2026-04-28T00:00:00+00:00", close=200.0),
        _forecast_bar("2026-04-29T00:00:00+00:00", close=201.0),
        _forecast_bar("2026-04-30T00:00:00+00:00", close=202.0),
    ]
    async with _db.SessionLocal() as session:
        session.add(
            AnalysisJob(
                id=job_id,
                status="done",
                inputs_json={"tickers": [ticker]},
                task_count=1,
                origin="self",
                submitted_at=started_at,
            )
        )
        session.add(
            AnalysisTask(
                id=task_id,
                job_id=job_id,
                ticker=ticker,
                interval="1d",
                model_id="kronos_base",
                status="done",
                started_at=started_at,
                finished_at=started_at,
                result_json={
                    "model_id": "kronos_base",
                    "horizon_bars": len(forecast),
                    "forecast": forecast,
                    "meta": {},
                },
            )
        )
        await session.commit()


# ----------------------------------------------------------------------
# explode_task
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explode_task_inserts_one_row_per_forecast_bar(client):
    await _seed_done_task()
    n = await predictions_svc.explode_task("task-1")
    assert n == 3

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(PredictionPoint).order_by(PredictionPoint.horizon_offset))).scalars().all()
    assert len(rows) == 3
    assert [r.horizon_offset for r in rows] == [1, 2, 3]
    assert [r.target_date for r in rows] == [
        datetime.date(2026, 4, 28),
        datetime.date(2026, 4, 29),
        datetime.date(2026, 4, 30),
    ]
    # Mon=0..Sun=6. 2026-04-27 is Monday.
    assert rows[0].made_on == datetime.date(2026, 4, 27)
    assert rows[0].made_on_dow == 0  # Monday
    assert rows[0].close == 200.0


@pytest.mark.asyncio
async def test_explode_task_idempotent(client):
    await _seed_done_task()
    a = await predictions_svc.explode_task("task-1")
    b = await predictions_svc.explode_task("task-1")
    async with _db.SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(PredictionPoint))
    assert a == b == 3
    assert count == 3  # second call replaced, didn't duplicate


@pytest.mark.asyncio
async def test_explode_task_skips_non_done(client):
    async with _db.SessionLocal() as session:
        session.add(AnalysisJob(id="j", status="done", inputs_json={}, task_count=1, origin="self"))
        session.add(AnalysisTask(
            id="t", job_id="j", ticker="X", interval="1d", model_id="kronos_base",
            status="ineligible",
        ))
        await session.commit()
    n = await predictions_svc.explode_task("t")
    assert n == 0


@pytest.mark.asyncio
async def test_explode_task_handles_friday_dow(client):
    # 2026-05-01 is a Friday → weekday()=4
    fri = datetime.datetime(2026, 5, 1, 14, 0, tzinfo=datetime.timezone.utc)
    await _seed_done_task(started_at=fri)
    await predictions_svc.explode_task("task-1")
    async with _db.SessionLocal() as session:
        row = (await session.execute(select(PredictionPoint).limit(1))).scalar_one()
    assert row.made_on_dow == 4


# ----------------------------------------------------------------------
# backfill_all
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_explodes_all_done_tasks(client):
    # Two done tasks, two ineligible.
    await _seed_done_task(task_id="t1", job_id="j1", ticker="AAPL")
    await _seed_done_task(task_id="t2", job_id="j2", ticker="MSFT")

    stats = await predictions_svc.backfill_all()
    assert stats["scanned"] == 2
    assert stats["exploded"] == 2
    assert stats["rows_inserted"] == 6  # 3 bars × 2 tasks


@pytest.mark.asyncio
async def test_backfill_only_missing_skips_already_exploded(client):
    await _seed_done_task()
    await predictions_svc.explode_task("task-1")

    stats = await predictions_svc.backfill_all(only_missing=True)
    assert stats["skipped"] == 1
    assert stats["exploded"] == 0


@pytest.mark.asyncio
async def test_backfill_route(client):
    await _seed_done_task()
    r = await client.post("/v1/predictions/backfill", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["exploded"] == 1
    assert body["rows_inserted"] == 3


# ----------------------------------------------------------------------
# explode_imported_tasks (via /v1/analysis/import)
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_job_auto_explodes(client):
    payload = {
        "schema_version": 1,
        "origin": "laptop",
        "job": {
            "id": "imp-1",
            "status": "done",
            "inputs_json": {},
            "task_count": 1,
            "submitted_at": "2026-04-27T12:00:00+00:00",
        },
        "tasks": [
            {
                "id": "imp-task-1",
                "ticker": "NVDA",
                "interval": "1d",
                "model_id": "kronos_base",
                "status": "done",
                "started_at": "2026-04-27T12:00:00+00:00",
                "finished_at": "2026-04-27T12:01:00+00:00",
                "result_json": {
                    "forecast": [
                        _forecast_bar("2026-04-28T00:00:00+00:00", close=300.0),
                        _forecast_bar("2026-04-29T00:00:00+00:00", close=301.0),
                    ]
                },
            }
        ],
    }
    r = await client.post("/v1/analysis/import", headers=HEADERS, json=payload)
    assert r.status_code == 200

    async with _db.SessionLocal() as session:
        rows = (await session.execute(
            select(PredictionPoint).where(PredictionPoint.task_id == "imp-task-1")
        )).scalars().all()
    assert len(rows) == 2
    assert rows[0].ticker == "NVDA"
    assert rows[0].made_on == datetime.date(2026, 4, 27)


@pytest.mark.asyncio
async def test_import_duplicate_does_not_duplicate_rows(client):
    payload = {
        "schema_version": 1,
        "job": {
            "id": "imp-2", "status": "done", "inputs_json": {}, "task_count": 1,
            "submitted_at": "2026-04-27T12:00:00+00:00",
        },
        "tasks": [{
            "id": "imp-task-2", "ticker": "AAPL", "interval": "1d", "model_id": "kronos_base",
            "status": "done",
            "started_at": "2026-04-27T12:00:00+00:00",
            "result_json": {"forecast": [_forecast_bar("2026-04-28T00:00:00+00:00")]},
        }],
    }
    await client.post("/v1/analysis/import", headers=HEADERS, json=payload)
    r2 = await client.post("/v1/analysis/import", headers=HEADERS, json=payload)
    assert r2.json()["status"] == "duplicate"

    async with _db.SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(PredictionPoint)
            .where(PredictionPoint.task_id == "imp-task-2")
        )
    assert count == 1


# ----------------------------------------------------------------------
# Cascade delete: deleting AnalysisTask removes its prediction_points.
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cascade_delete_on_task_removes_rows(client):
    await _seed_done_task()
    await predictions_svc.explode_task("task-1")

    async with _db.SessionLocal() as session:
        task = await session.get(AnalysisTask, "task-1")
        await session.delete(task)
        await session.commit()
        count = await session.scalar(select(func.count()).select_from(PredictionPoint))
    assert count == 0
