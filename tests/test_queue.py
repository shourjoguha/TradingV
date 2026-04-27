"""Submit-queue tests — Tier 1.

Strategy:
- Service-level: enqueue, list, get, cancel, claim_next, mark_done/failed,
  reset_stuck_on_boot. Pure DB tests.
- Worker integration: spin worker_loop briefly, assert it claims and
  processes items end-to-end (with submit_run monkeypatched to a no-op
  so we don't need real Kronos in tests).
- Routes: 202 on /v1/analysis/run, 400 on bad input, 200 on list/get,
  204/200 on cancel, 409 on cancel-running, 404 on cancel-missing.
"""
from __future__ import annotations

import asyncio
import datetime
import uuid

import pytest
from sqlalchemy import select

from app.analysis.models import AnalysisJob
from app.core import db as _db
from app.queue import service as qsvc, worker as qworker
from app.queue.models import SubmitQueueItem

HEADERS = {"X-API-Key": "test-key"}


# ----------------------------------------------------------------------
# Service unit tests
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_creates_pending_row(client):
    item = await qsvc.enqueue(
        inputs={"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": None, "horizon_bars": 5},
        source="manual",
    )
    assert item["status"] == "pending"
    assert item["source"] == "manual"
    assert item["job_id"] is None
    assert item["finished_at"] is None

    fetched = await qsvc.get(item["id"])
    assert fetched is not None
    assert fetched["id"] == item["id"]


@pytest.mark.asyncio
async def test_enqueue_invalid_source_raises(client):
    with pytest.raises(ValueError):
        await qsvc.enqueue(inputs={}, source="garbage")


@pytest.mark.asyncio
async def test_list_items_filters_by_status(client):
    await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    await qsvc.enqueue(inputs={"tickers": ["B"], "intervals": ["1d"]}, source="schedule")

    pending = await qsvc.list_items(status="pending")
    assert len(pending) == 2

    done = await qsvc.list_items(status="done")
    assert done == []


@pytest.mark.asyncio
async def test_cancel_pending_succeeds(client):
    item = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    ok, status = await qsvc.cancel(item["id"])
    assert ok is True
    assert status == "cancelled"

    after = await qsvc.get(item["id"])
    assert after["status"] == "cancelled"
    assert after["finished_at"] is not None


@pytest.mark.asyncio
async def test_cancel_missing_returns_not_found(client):
    ok, status = await qsvc.cancel("does-not-exist")
    assert ok is False
    assert status == "not_found"


@pytest.mark.asyncio
async def test_cancel_running_returns_false(client):
    item = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    # Manually flip to 'running' to simulate the worker having claimed it.
    async with _db.SessionLocal() as session:
        row = await session.get(SubmitQueueItem, item["id"])
        row.status = "running"
        row.started_at = datetime.datetime.now(datetime.timezone.utc)
        await session.commit()

    ok, status = await qsvc.cancel(item["id"])
    assert ok is False
    assert status == "running"


@pytest.mark.asyncio
async def test_claim_next_picks_oldest_pending_fifo(client):
    a = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    # Make `a` clearly older.
    await asyncio.sleep(0.01)
    b = await qsvc.enqueue(inputs={"tickers": ["B"], "intervals": ["1d"]}, source="manual")

    async with _db.SessionLocal() as session:
        first = await qsvc.claim_next(session)
        await session.commit()
    assert first.id == a["id"]

    async with _db.SessionLocal() as session:
        second = await qsvc.claim_next(session)
        await session.commit()
    assert second.id == b["id"]

    async with _db.SessionLocal() as session:
        third = await qsvc.claim_next(session)
    assert third is None


@pytest.mark.asyncio
async def test_claim_next_sets_running_and_started_at(client):
    item = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    async with _db.SessionLocal() as session:
        claimed = await qsvc.claim_next(session)
        await session.commit()
    assert claimed.status == "running"
    assert claimed.started_at is not None


@pytest.mark.asyncio
async def test_mark_done_sets_finished_and_job_id(client):
    # Create a real AnalysisJob so the FK constraint is satisfied.
    async with _db.SessionLocal() as session:
        job = AnalysisJob(inputs_json={}, status="done", task_count=0)
        session.add(job)
        await session.commit()
        job_id = job.id

    item = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    await qsvc.mark_done(item["id"], job_id=job_id)

    after = await qsvc.get(item["id"])
    assert after["status"] == "done"
    assert after["job_id"] == job_id
    assert after["finished_at"] is not None


@pytest.mark.asyncio
async def test_mark_failed_records_error(client):
    item = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    await qsvc.mark_failed(item["id"], error="boom")

    after = await qsvc.get(item["id"])
    assert after["status"] == "failed"
    assert after["error"] == "boom"


@pytest.mark.asyncio
async def test_reset_stuck_on_boot_flips_running_to_pending(client):
    item = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    async with _db.SessionLocal() as session:
        row = await session.get(SubmitQueueItem, item["id"])
        row.status = "running"
        row.started_at = datetime.datetime.now(datetime.timezone.utc)
        await session.commit()

    n = await qsvc.reset_stuck_on_boot()
    assert n == 1

    after = await qsvc.get(item["id"])
    assert after["status"] == "pending"
    assert after["started_at"] is None


@pytest.mark.asyncio
async def test_queue_stats_groups_by_status(client):
    a = await qsvc.enqueue(inputs={"tickers": ["A"], "intervals": ["1d"]}, source="manual")
    b = await qsvc.enqueue(inputs={"tickers": ["B"], "intervals": ["1d"]}, source="manual")
    await qsvc.cancel(a["id"])

    stats = await qsvc.queue_stats()
    assert stats["pending"] == 1
    assert stats["cancelled"] == 1
    assert stats["done"] == 0


# ----------------------------------------------------------------------
# Worker integration test — spin loop briefly with submit_run mocked
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_loop_processes_pending_to_done(client, monkeypatch):
    # Mock analysis.service.submit_run to avoid pulling real Kronos.
    fake_job_id = str(uuid.uuid4())

    async def fake_submit_run(**kwargs):
        # Simulate the real shape: returns an AnalysisJob with .id.
        async with _db.SessionLocal() as session:
            job = AnalysisJob(id=fake_job_id, inputs_json=kwargs, status="done", task_count=1)
            session.add(job)
            await session.commit()
        return job

    from app.analysis import service as asvc

    monkeypatch.setattr(asvc, "submit_run", fake_submit_run)

    item = await qsvc.enqueue(
        inputs={"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": None, "horizon_bars": 5},
        source="manual",
    )

    # Run the worker briefly; cancel after we see status=done.
    stop = asyncio.Event()
    task = asyncio.create_task(qworker.worker_loop(stop_event=stop))

    # Poll up to 3s for the worker to finish.
    deadline = asyncio.get_event_loop().time() + 3.0
    while asyncio.get_event_loop().time() < deadline:
        snap = await qsvc.get(item["id"])
        if snap and snap["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)

    stop.set()
    qworker.request_wake()  # Cut the inner sleep so loop exits promptly.
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()

    final = await qsvc.get(item["id"])
    assert final["status"] == "done"
    assert final["job_id"] == fake_job_id


@pytest.mark.asyncio
async def test_worker_marks_failed_on_exception(client, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("kaboom")

    from app.analysis import service as asvc

    monkeypatch.setattr(asvc, "submit_run", boom)

    item = await qsvc.enqueue(
        inputs={"tickers": ["AAPL"], "intervals": ["1d"]},
        source="manual",
    )

    stop = asyncio.Event()
    task = asyncio.create_task(qworker.worker_loop(stop_event=stop))

    deadline = asyncio.get_event_loop().time() + 3.0
    while asyncio.get_event_loop().time() < deadline:
        snap = await qsvc.get(item["id"])
        if snap and snap["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)

    stop.set()
    qworker.request_wake()
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()

    final = await qsvc.get(item["id"])
    assert final["status"] == "failed"
    assert "kaboom" in (final["error"] or "")


# ----------------------------------------------------------------------
# Route tests
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_route_returns_202_and_queues(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"]},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["queue_id"]
    assert body["job_id"] is None


@pytest.mark.asyncio
async def test_run_route_validates_inputs(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["bogus_interval"]},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_queue_list_route(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"]},
    )
    assert r.status_code == 202

    r2 = await client.get("/v1/analysis/queue", headers=HEADERS)
    assert r2.status_code == 200
    body = r2.json()
    assert body["count"] >= 1


@pytest.mark.asyncio
async def test_queue_get_route(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"]},
    )
    qid = r.json()["queue_id"]

    r2 = await client.get(f"/v1/analysis/queue/{qid}", headers=HEADERS)
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == qid


@pytest.mark.asyncio
async def test_queue_get_missing_returns_404(client):
    r = await client.get("/v1/analysis/queue/missing", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_queue_cancel_pending(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"]},
    )
    qid = r.json()["queue_id"]

    r2 = await client.delete(f"/v1/analysis/queue/{qid}", headers=HEADERS)
    assert r2.status_code == 200
    assert r2.json()["cancelled"] is True


@pytest.mark.asyncio
async def test_queue_cancel_missing(client):
    r = await client.delete("/v1/analysis/queue/missing", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_queue_stats_route(client):
    r = await client.get("/v1/analysis/queue/stats", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"pending", "running", "done", "failed", "cancelled"}
