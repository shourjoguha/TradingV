"""Phase B3 — replicate watchlist / schedule / labels via outbox.

Tests cover:
- Each external CRUD enqueues the right kind+payload.
- Drain dispatches to the right peer_client.push_* function.
- Receiver endpoints (/v1/{watchlist,schedule,labels}/import) apply changes
  WITHOUT re-enqueueing (loop avoidance).
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.core import db as _db
from app.labels.models import TickerLabel
from app.schedule import service as schedule_svc
from app.schedule.models import ScheduleConfig
from app.sync import peer_client
from app.sync import service as sync_svc
from app.sync.models import SyncOutbox
from app.watchlist.models import WatchlistEntry

HEADERS = {"X-API-Key": "test-key"}


# ----------------------------------------------------------------------
# Watchlist replication
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watchlist_add_enqueues_replication(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    r = await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    assert r.status_code == 201

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    watchlist_rows = [r for r in rows if r.kind == "watchlist"]
    assert len(watchlist_rows) == 1
    payload = watchlist_rows[0].payload_json
    assert payload["action"] == "upsert"
    assert payload["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_watchlist_delete_enqueues_replication(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    r = await client.delete("/v1/watchlist/AAPL", headers=HEADERS)
    assert r.status_code == 204

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    delete_rows = [
        r for r in rows if r.kind == "watchlist" and r.payload_json.get("action") == "delete"
    ]
    assert len(delete_rows) == 1
    assert delete_rows[0].payload_json["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_watchlist_no_replication_when_peer_unconfigured(client):
    # peer_configured() defaults False with PEER_API_URL="" in test env.
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_watchlist_import_endpoint_applies_change(client):
    r = await client.post(
        "/v1/watchlist/import",
        headers=HEADERS,
        json={"action": "upsert", "symbol": "AAPL", "notes": "from peer"},
    )
    assert r.status_code == 200
    assert r.json()["result"] == "upsert"

    async with _db.SessionLocal() as session:
        entry = await session.get(WatchlistEntry, "AAPL")
    assert entry is not None
    assert entry.notes == "from peer"


@pytest.mark.asyncio
async def test_watchlist_import_does_not_reenqueue(client, monkeypatch):
    """Loop avoidance: receiver writes must not trigger another outbox push."""
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.post(
        "/v1/watchlist/import",
        headers=HEADERS,
        json={"action": "upsert", "symbol": "AAPL"},
    )

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    # Receiver should have written to watchlist directly without enqueueing.
    assert rows == []


@pytest.mark.asyncio
async def test_watchlist_import_delete(client):
    # Seed the entry directly via the import path so we don't enqueue.
    await client.post(
        "/v1/watchlist/import",
        headers=HEADERS,
        json={"action": "upsert", "symbol": "AAPL"},
    )
    r = await client.post(
        "/v1/watchlist/import",
        headers=HEADERS,
        json={"action": "delete", "symbol": "AAPL"},
    )
    assert r.json()["result"] == "delete"

    async with _db.SessionLocal() as session:
        assert await session.get(WatchlistEntry, "AAPL") is None


# ----------------------------------------------------------------------
# Schedule replication
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_update_enqueues_replication(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    r = await client.put(
        "/v1/schedule", headers=HEADERS, json={"enabled": True, "horizon_bars": 7}
    )
    assert r.status_code == 200

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    sched_rows = [r for r in rows if r.kind == "schedule"]
    assert len(sched_rows) == 1
    payload = sched_rows[0].payload_json
    assert payload["enabled"] is True
    assert payload["horizon_bars"] == 7
    # Local-only fields must NOT be in the replication payload.
    assert "pending_run" not in payload
    assert "last_run_at" not in payload
    assert "next_run_at" not in payload


@pytest.mark.asyncio
async def test_schedule_import_preserves_runtime_state(client):
    # Set a known runtime state locally.
    await schedule_svc.update_config(enabled=False)
    await schedule_svc.set_pending(True)
    async with _db.SessionLocal() as session:
        cfg = await session.get(ScheduleConfig, 1)
        cfg.last_run_status = "succeeded"
        cfg.last_run_at = datetime.datetime(2026, 4, 25, tzinfo=datetime.timezone.utc)
        await session.commit()

    # Simulate a peer push that turns enabled on + bumps horizon.
    r = await client.post(
        "/v1/schedule/import",
        headers=HEADERS,
        json={"enabled": True, "horizon_bars": 9, "model_ids": ["kronos_base"],
              "intervals": ["1d"], "tz_name": "UTC", "run_at_local": "23:30:00",
              "retry_minutes": 5, "collect_actuals": True, "skip_weekends": True},
    )
    assert r.status_code == 200
    body = r.json()
    # Imported fields applied.
    assert body["enabled"] is True
    assert body["horizon_bars"] == 9
    # Runtime state preserved.
    assert body["pending_run"] is True
    assert body["last_run_status"] == "succeeded"


@pytest.mark.asyncio
async def test_schedule_import_does_not_reenqueue(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.post(
        "/v1/schedule/import",
        headers=HEADERS,
        json={"enabled": True, "tz_name": "UTC", "run_at_local": "23:30:00",
              "intervals": ["1d"], "horizon_bars": 5, "model_ids": ["kronos_base"],
              "retry_minutes": 5, "collect_actuals": True, "skip_weekends": True},
    )

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert rows == []


# ----------------------------------------------------------------------
# Labels replication
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_label_put_enqueues_replication(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    label_rows = [r for r in rows if r.kind == "label"]
    assert len(label_rows) == 1
    p = label_rows[0].payload_json
    assert p == {"action": "upsert", "symbol": "AAPL", "key": "sector", "value": "tech"}


@pytest.mark.asyncio
async def test_label_bulk_upsert_enqueues_one_per_key(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.put(
        "/v1/tickers/AAPL/labels",
        headers=HEADERS,
        json={"labels": {"sector": "tech", "capsize": "large"}},
    )

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    label_rows = [r for r in rows if r.kind == "label"]
    assert len(label_rows) == 2
    keys = {r.payload_json["key"] for r in label_rows}
    assert keys == {"sector", "capsize"}


@pytest.mark.asyncio
async def test_label_delete_enqueues_replication(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )
    await client.delete("/v1/tickers/AAPL/labels/sector", headers=HEADERS)

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    delete_rows = [
        r for r in rows
        if r.kind == "label" and r.payload_json.get("action") == "delete"
    ]
    assert len(delete_rows) == 1
    assert delete_rows[0].payload_json == {
        "action": "delete", "symbol": "AAPL", "key": "sector"
    }


@pytest.mark.asyncio
async def test_label_import_applies_change(client):
    r = await client.post(
        "/v1/labels/import",
        headers=HEADERS,
        json={"action": "upsert", "symbol": "AAPL", "key": "sector", "value": "tech"},
    )
    assert r.json()["result"] == "upsert"

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(TickerLabel))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "tech"


@pytest.mark.asyncio
async def test_label_import_does_not_reenqueue(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    await client.post(
        "/v1/labels/import",
        headers=HEADERS,
        json={"action": "upsert", "symbol": "AAPL", "key": "sector", "value": "tech"},
    )

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert rows == []


# ----------------------------------------------------------------------
# Drain dispatch — confirms each kind hits the right peer_client function.
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_drain_dispatches_each_kind(client, monkeypatch):
    monkeypatch.setattr(sync_svc, "peer_configured", lambda: True)
    monkeypatch.setattr(
        sync_svc.SETTINGS, "PEER_API_URL", "http://peer", raising=False
    )

    pushed: dict[str, list] = {"watchlist": [], "schedule": [], "label": []}

    async def fake_watchlist(*, peer_url, api_key, payload):
        pushed["watchlist"].append(payload)
        return True, None

    async def fake_schedule(*, peer_url, api_key, payload):
        pushed["schedule"].append(payload)
        return True, None

    async def fake_label(*, peer_url, api_key, payload):
        pushed["label"].append(payload)
        return True, None

    monkeypatch.setattr(peer_client, "push_watchlist", fake_watchlist)
    monkeypatch.setattr(peer_client, "push_schedule", fake_schedule)
    monkeypatch.setattr(peer_client, "push_label", fake_label)

    await sync_svc.enqueue_kind("watchlist", {"action": "upsert", "symbol": "AAPL"})
    await sync_svc.enqueue_kind("schedule", {"enabled": True})
    await sync_svc.enqueue_kind(
        "label", {"action": "upsert", "symbol": "AAPL", "key": "sector", "value": "tech"}
    )

    stats = await sync_svc.drain_outbox()
    assert stats == {"ok": 3, "failed": 0, "scanned": 3}
    assert pushed["watchlist"][0]["symbol"] == "AAPL"
    assert pushed["schedule"][0]["enabled"] is True
    assert pushed["label"][0]["key"] == "sector"
