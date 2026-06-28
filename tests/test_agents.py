"""Agents lane (TradingAgents side-by-side with Kronos)."""
from __future__ import annotations

import pytest

from app.core.config import SETTINGS

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def debug_stub():
    """Enable the deterministic stub engine for the duration of a test."""
    prev = SETTINGS.DEBUG_STUB
    SETTINGS.DEBUG_STUB = True
    try:
        yield
    finally:
        SETTINGS.DEBUG_STUB = prev


@pytest.mark.asyncio
async def test_engine_info_defaults(client):
    r = await client.get("/v1/agents/engine", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False  # ships dark
    assert body["active_engine"] == "stub"
    assert set(body["stances"]) == {"BUY", "SELL", "HOLD"}


@pytest.mark.asyncio
async def test_run_without_engine_returns_422(client):
    # DEBUG_STUB off + AGENTS_ENABLED off => stub refuses, surfaced as 422.
    r = await client.post("/v1/agents/run", headers=HEADERS, json={"ticker": "AAPL"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_run_ticker_stub_creates_and_is_idempotent(client, debug_stub):
    r = await client.post("/v1/agents/run", headers=HEADERS, json={"ticker": "aapl"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert body["ticker"] == "AAPL"
    assert body["stance"] in {"BUY", "SELL", "HOLD"}

    # Second run same ticker/day => no duplicate row.
    r2 = await client.post("/v1/agents/run", headers=HEADERS, json={"ticker": "AAPL"})
    assert r2.status_code == 200
    assert r2.json()["created"] is False

    # And it shows up in the listing.
    lst = await client.get("/v1/agents/decisions?ticker=AAPL", headers=HEADERS)
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_run_watchlist_stub(client, debug_stub):
    for sym in ("AAPL", "MSFT"):
        await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": sym})
    r = await client.post("/v1/agents/run", headers=HEADERS, json={})
    assert r.status_code == 200
    stats = r.json()
    assert stats["scanned"] == 2
    assert stats["created"] == 2
    assert stats["failed"] == 0


@pytest.mark.asyncio
async def test_decisions_rejects_bad_stance_filter(client):
    r = await client.get("/v1/agents/decisions?stance=MAYBE", headers=HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_agents_lane_does_not_touch_opportunities(client, debug_stub):
    """The agent lane is independent: running it writes NOTHING to the
    Kronos-bound opportunities feed."""
    await client.post("/v1/agents/run", headers=HEADERS, json={"ticker": "NVDA"})
    opps = await client.get("/v1/opportunities", headers=HEADERS)
    assert opps.status_code == 200
    assert opps.json()["items"] == []
