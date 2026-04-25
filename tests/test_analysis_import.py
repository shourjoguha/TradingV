"""Tests for /v1/analysis/import — peer-replicated job receiver.

Covers:
- Successful import inserts job + tasks tagged origin='peer'
- Duplicate import is idempotent (returns 'duplicate', no second insert)
- Malformed payloads return 400
- Imported jobs do NOT trigger downstream sync (loop avoidance)
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.sync import service as sync_service

HEADERS = {"X-API-Key": "test-key"}


def _make_payload(job_id: str = "job-import-1") -> dict:
    return {
        "schema_version": 1,
        "origin": "laptop",
        "job": {
            "id": job_id,
            "status": "done",
            "inputs_json": {"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_base"]},
            "task_count": 1,
            "submitted_at": "2026-04-25T10:00:00+00:00",
            "finished_at": "2026-04-25T10:05:00+00:00",
        },
        "tasks": [
            {
                "id": "task-1",
                "ticker": "AAPL",
                "interval": "1d",
                "model_id": "kronos_base",
                "status": "done",
                "result_json": {"forecast": [{"close": 100.0}]},
                "started_at": "2026-04-25T10:00:01+00:00",
                "finished_at": "2026-04-25T10:05:00+00:00",
            }
        ],
    }


@pytest.mark.asyncio
async def test_import_inserts_job_with_origin_peer(client):
    r = await client.post("/v1/analysis/import", headers=HEADERS, json=_make_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"job_id": "job-import-1", "status": "imported"}

    async with _db.SessionLocal() as session:
        job = await session.get(AnalysisJob, "job-import-1")
        assert job is not None
        assert job.origin == "peer"
        assert job.status == "done"
        tasks = (
            await session.execute(select(AnalysisTask).where(AnalysisTask.job_id == "job-import-1"))
        ).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].result_json == {"forecast": [{"close": 100.0}]}


@pytest.mark.asyncio
async def test_import_is_idempotent_on_duplicate(client):
    p = _make_payload("job-dup")
    r1 = await client.post("/v1/analysis/import", headers=HEADERS, json=p)
    assert r1.json()["status"] == "imported"
    r2 = await client.post("/v1/analysis/import", headers=HEADERS, json=p)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"

    async with _db.SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(AnalysisJob))
        assert count == 1


@pytest.mark.asyncio
async def test_import_rejects_bad_schema_version(client):
    p = _make_payload("job-bad")
    p["schema_version"] = 99
    r = await client.post("/v1/analysis/import", headers=HEADERS, json=p)
    assert r.status_code == 400
    assert "schema_version" in r.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_missing_job_id(client):
    p = _make_payload("job-x")
    p["job"]["id"] = ""
    r = await client.post("/v1/analysis/import", headers=HEADERS, json=p)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_imported_job_does_not_trigger_replication(client, monkeypatch):
    """Loop avoidance: origin='peer' jobs must not enqueue sync rows."""
    enqueue_calls: list = []
    enqueue_result_calls: list = []

    async def fake_enqueue(pairs):
        enqueue_calls.append(list(pairs))
        return 0

    async def fake_enqueue_result(payload):
        enqueue_result_calls.append(payload)
        return 0

    monkeypatch.setattr(sync_service, "peer_configured", lambda: True)
    monkeypatch.setattr(sync_service, "enqueue", fake_enqueue)
    monkeypatch.setattr(sync_service, "enqueue_result", fake_enqueue_result)

    r = await client.post("/v1/analysis/import", headers=HEADERS, json=_make_payload("job-loop"))
    assert r.status_code == 200

    # Importing inserts directly (no _process_job) — neither queue should fire.
    assert enqueue_calls == []
    assert enqueue_result_calls == []
