"""Surgical admin endpoints for one-shot cleanup of stuck rows."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.sync.models import SyncOutbox

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_delete_outbox_row(client):
    async with _db.SessionLocal() as session:
        row = SyncOutbox(
            peer_url="http://broken-no-port",
            kind="result",
            payload_json={"x": 1},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id

    r = await client.delete(f"/v1/sync/outbox/{row_id}", headers=HEADERS)
    assert r.status_code == 204

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_outbox_row_404_when_missing(client):
    r = await client.delete("/v1/sync/outbox/nonexistent-id", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_abort_job_marks_running_tasks_as_error(client):
    """Stuck running job + tasks → all flipped to terminal state."""
    async with _db.SessionLocal() as session:
        session.add(
            AnalysisJob(
                id="stuck-1", status="running", inputs_json={}, task_count=2,
                origin="self",
            )
        )
        session.add(
            AnalysisTask(
                id="t1", job_id="stuck-1", ticker="AAPL", interval="1d",
                model_id="kronos_base", status="running",
                started_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        session.add(
            AnalysisTask(
                id="t2", job_id="stuck-1", ticker="MSFT", interval="1d",
                model_id="kronos_base", status="pending",
            )
        )
        await session.commit()

    r = await client.post("/v1/analysis/jobs/stuck-1/abort", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["finished_at"] is not None
    statuses = sorted(t["status"] for t in body["tasks"])
    assert statuses == ["error", "error"]
    for t in body["tasks"]:
        assert "aborted" in (t.get("error") or "").lower()


@pytest.mark.asyncio
async def test_abort_job_preserves_already_done_tasks(client):
    """A task that genuinely finished must not be downgraded to error."""
    async with _db.SessionLocal() as session:
        session.add(
            AnalysisJob(
                id="mixed-1", status="running", inputs_json={}, task_count=2,
                origin="self",
            )
        )
        session.add(
            AnalysisTask(
                id="done-1", job_id="mixed-1", ticker="AAPL", interval="1d",
                model_id="kronos_base", status="done",
                result_json={"forecast": []},
            )
        )
        session.add(
            AnalysisTask(
                id="run-1", job_id="mixed-1", ticker="MSFT", interval="1d",
                model_id="kronos_base", status="running",
            )
        )
        await session.commit()

    r = await client.post("/v1/analysis/jobs/mixed-1/abort", headers=HEADERS)
    body = r.json()
    by_id = {t["id"]: t for t in body["tasks"]}
    assert by_id["done-1"]["status"] == "done"
    assert by_id["run-1"]["status"] == "error"


@pytest.mark.asyncio
async def test_abort_job_idempotent(client):
    async with _db.SessionLocal() as session:
        session.add(
            AnalysisJob(
                id="idem-1", status="done", inputs_json={}, task_count=1,
                origin="self",
                finished_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        session.add(
            AnalysisTask(
                id="idem-t1", job_id="idem-1", ticker="AAPL", interval="1d",
                model_id="kronos_base", status="done",
            )
        )
        await session.commit()

    # Second abort on already-terminal job should still work + not corrupt state.
    r = await client.post("/v1/analysis/jobs/idem-1/abort", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["tasks"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_abort_job_404_when_missing(client):
    r = await client.post("/v1/analysis/jobs/ghost/abort", headers=HEADERS)
    assert r.status_code == 404
