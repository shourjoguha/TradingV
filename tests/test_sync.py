"""Sync outbox + peer client tests.

peer_client.push_ticker is monkeypatched to avoid real HTTP. Focus is on:
- enqueue creates rows
- drain_outbox marks success / backs off failure
- manual retry endpoint re-drains
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.core import db as _db
from app.sync import peer_client, service as sync_service
from app.sync.models import SyncOutbox

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def _peer_configured(monkeypatch):
    monkeypatch.setattr(sync_service, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_service.SETTINGS, "PEER_API_URL", "http://peer.test", raising=False
    )
    monkeypatch.setattr(
        sync_service.SETTINGS, "PEER_API_KEY", "peer-key", raising=False
    )


@pytest.mark.asyncio
async def test_enqueue_creates_rows(client, monkeypatch):
    n = await sync_service.enqueue([("AAPL", "stock"), ("BTCUSD", "crypto")])
    assert n == 2

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
        assert {r.symbol for r in rows} == {"AAPL", "BTCUSD"}
        assert all(r.completed_at is None for r in rows)
        assert all(r.attempts == 0 for r in rows)


@pytest.mark.asyncio
async def test_drain_outbox_marks_complete_on_success(client, monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_push(*, peer_url, api_key, symbol, asset_class):
        calls.append((symbol, asset_class))
        return True, None

    monkeypatch.setattr(peer_client, "push_ticker", fake_push)

    await sync_service.enqueue([("AAPL", "stock")])
    stats = await sync_service.drain_outbox()
    assert stats == {"ok": 1, "failed": 0, "scanned": 1}
    assert calls == [("AAPL", "stock")]

    async with _db.SessionLocal() as session:
        row = (await session.execute(select(SyncOutbox))).scalar_one()
        assert row.completed_at is not None
        assert row.attempts == 1
        assert row.last_error is None


@pytest.mark.asyncio
async def test_drain_outbox_backs_off_on_failure(client, monkeypatch):
    async def fake_push(**_kwargs):
        return False, "http_503: down"

    monkeypatch.setattr(peer_client, "push_ticker", fake_push)

    await sync_service.enqueue([("AAPL", "stock")])
    stats = await sync_service.drain_outbox()
    assert stats == {"ok": 0, "failed": 1, "scanned": 1}

    async with _db.SessionLocal() as session:
        row = (await session.execute(select(SyncOutbox))).scalar_one()
        assert row.completed_at is None
        assert row.attempts == 1
        assert row.last_error == "http_503: down"
        # Backoff pushed next_retry_at at least 25s into the future.
        # SQLite drops tzinfo; compare naively.
        nr = row.next_retry_at.replace(tzinfo=None)
        delta = nr - datetime.datetime.utcnow()
        assert delta.total_seconds() > 25


@pytest.mark.asyncio
async def test_manual_retry_endpoint_redrains(client, monkeypatch):
    async def fake_push(**_kwargs):
        return True, None

    monkeypatch.setattr(peer_client, "push_ticker", fake_push)

    await sync_service.enqueue([("AAPL", "stock")])
    r = await client.post("/v1/sync/retry", headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": 1, "failed": 0, "scanned": 1}


@pytest.mark.asyncio
async def test_list_outbox_filters_by_status(client, monkeypatch):
    async def ok_push(**_kwargs):
        return True, None

    monkeypatch.setattr(peer_client, "push_ticker", ok_push)
    await sync_service.enqueue([("AAPL", "stock")])
    await sync_service.drain_outbox()

    async def fail_push(**_kwargs):
        return False, "boom"

    monkeypatch.setattr(peer_client, "push_ticker", fail_push)
    await sync_service.enqueue([("MSFT", "stock")])
    await sync_service.drain_outbox()

    r = await client.get("/v1/sync/outbox?status=completed", headers=HEADERS)
    assert r.status_code == 200
    assert [row["symbol"] for row in r.json()["rows"]] == ["AAPL"]

    r = await client.get("/v1/sync/outbox?status=failed", headers=HEADERS)
    assert r.status_code == 200
    assert [row["symbol"] for row in r.json()["rows"]] == ["MSFT"]


@pytest.mark.asyncio
async def test_enqueue_result_creates_result_row(client, monkeypatch):
    payload = {
        "schema_version": 1,
        "origin": "laptop",
        "job": {"id": "abc-123", "status": "done", "inputs_json": {}, "task_count": 0,
                "submitted_at": "2026-04-25T10:00:00+00:00", "finished_at": None},
        "tasks": [],
    }
    n = await sync_service.enqueue_result(payload)
    assert n == 1

    async with _db.SessionLocal() as session:
        row = (await session.execute(select(SyncOutbox))).scalar_one()
        assert row.kind == "result"
        assert row.symbol is None
        assert row.payload_json["job"]["id"] == "abc-123"


@pytest.mark.asyncio
async def test_drain_routes_result_rows_to_push_result(client, monkeypatch):
    ticker_calls: list[tuple] = []
    result_calls: list[dict] = []

    async def fake_push_ticker(*, peer_url, api_key, symbol, asset_class):
        ticker_calls.append((symbol, asset_class))
        return True, None

    async def fake_push_result(*, peer_url, api_key, payload):
        result_calls.append(payload)
        return True, None

    monkeypatch.setattr(peer_client, "push_ticker", fake_push_ticker)
    monkeypatch.setattr(peer_client, "push_result", fake_push_result)

    await sync_service.enqueue([("AAPL", "stock")])
    await sync_service.enqueue_result({"schema_version": 1, "job": {"id": "j1"}, "tasks": []})

    stats = await sync_service.drain_outbox()
    assert stats == {"ok": 2, "failed": 0, "scanned": 2}
    assert ticker_calls == [("AAPL", "stock")]
    assert len(result_calls) == 1
    assert result_calls[0]["job"]["id"] == "j1"


def test_backoff_schedule_exponential():
    assert (sync_service._backoff(1) - sync_service._now()).total_seconds() > 25
    assert (sync_service._backoff(2) - sync_service._now()).total_seconds() > 55
    assert (sync_service._backoff(3) - sync_service._now()).total_seconds() > 115
    # Capped at 1h.
    capped = (sync_service._backoff(20) - sync_service._now()).total_seconds()
    assert capped <= 3600 + 1
