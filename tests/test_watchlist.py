"""Watchlist CRUD + bulk add + auto-upsert into ticker registry."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core import db as _db
from app.tickers.models import Ticker
from app.watchlist.models import WatchlistEntry

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_add_creates_ticker_and_watchlist_entry(client):
    r = await client.post(
        "/v1/watchlist", headers=HEADERS, json={"symbol": "aapl", "notes": "tech"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["symbol"] == "AAPL"  # normalised uppercase
    assert body["notes"] == "tech"

    async with _db.SessionLocal() as session:
        # Watchlist entry persisted
        entry = await session.get(WatchlistEntry, "AAPL")
        assert entry is not None
        # Ticker registry auto-upserted
        ticker = await session.get(Ticker, "AAPL")
        assert ticker is not None


@pytest.mark.asyncio
async def test_add_idempotent(client):
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    r2 = await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    assert r2.status_code == 201

    r3 = await client.get("/v1/watchlist", headers=HEADERS)
    assert r3.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_returns_entries(client):
    for s in ("AAPL", "MSFT", "NVDA"):
        await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": s})
    r = await client.get("/v1/watchlist", headers=HEADERS)
    body = r.json()
    assert body["count"] == 3
    assert {e["symbol"] for e in body["entries"]} == {"AAPL", "MSFT", "NVDA"}


@pytest.mark.asyncio
async def test_get_single_entry(client):
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    r = await client.get("/v1/watchlist/AAPL", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["symbol"] == "AAPL"

    r2 = await client.get("/v1/watchlist/MISSING", headers=HEADERS)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_patch_updates_notes(client):
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    r = await client.patch(
        "/v1/watchlist/AAPL", headers=HEADERS, json={"notes": "earnings tomorrow"}
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "earnings tomorrow"


@pytest.mark.asyncio
async def test_delete_removes_only_watchlist_row(client):
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})

    r = await client.delete("/v1/watchlist/AAPL", headers=HEADERS)
    assert r.status_code == 204

    # Watchlist gone
    async with _db.SessionLocal() as session:
        assert await session.get(WatchlistEntry, "AAPL") is None
        # Ticker registry preserved (removal must not cascade up)
        assert await session.get(Ticker, "AAPL") is not None


@pytest.mark.asyncio
async def test_delete_missing_returns_404(client):
    r = await client.delete("/v1/watchlist/GHOST", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_bulk_add(client):
    r = await client.post(
        "/v1/watchlist/bulk",
        headers=HEADERS,
        json={"symbols": ["aapl", "msft", "nvda", "AAPL"]},  # dup + lowercase
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == 4
    assert body["added"] == 3  # AAPL only counted once

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(WatchlistEntry))).scalars().all()
        assert {r.symbol for r in rows} == {"AAPL", "MSFT", "NVDA"}


@pytest.mark.asyncio
async def test_bulk_add_empty_400(client):
    r = await client.post("/v1/watchlist/bulk", headers=HEADERS, json={"symbols": []})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unauthenticated(client):
    r = await client.get("/v1/watchlist")
    assert r.status_code in (401, 403)
