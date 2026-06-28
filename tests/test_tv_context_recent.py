"""GET /v1/tv-context/recent — recent active items across all tickers."""
from __future__ import annotations

import datetime

import pytest

import app.core.db as core_db
from app.tv_context import service as tvc_service
from app.tv_context.models import STATUS_EXPIRED

HEADERS = {"X-API-Key": "test-key"}


async def _seed_three(client):
    """Ingest 3 webhooks (distinct tickers => no dedupe) and stamp deterministic
    captured_at so ordering is testable. Returns tickers oldest->newest."""
    base = datetime.datetime(2026, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    order = ["AAPL", "MSFT", "NVDA"]  # oldest -> newest
    async with core_db.SessionLocal() as session:
        for i, tkr in enumerate(order):
            item, _ = await tvc_service.ingest_webhook(
                session=session,
                ticker=tkr,
                alert_type="rsi_cross",
                payload_json={"i": i},
            )
            item.captured_at = base + datetime.timedelta(minutes=i)
        await session.commit()
    return order


@pytest.mark.asyncio
async def test_recent_returns_newest_first(client):
    await _seed_three(client)
    r = await client.get("/v1/tv-context/recent", headers=HEADERS)
    assert r.status_code == 200
    tickers = [it["ticker"] for it in r.json()]
    assert tickers == ["NVDA", "MSFT", "AAPL"]  # newest -> oldest
    assert all(it["status"] == "active" for it in r.json())


@pytest.mark.asyncio
async def test_recent_respects_limit(client):
    await _seed_three(client)
    r = await client.get("/v1/tv-context/recent?limit=2", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert [it["ticker"] for it in body] == ["NVDA", "MSFT"]


@pytest.mark.asyncio
async def test_recent_excludes_expired(client):
    await _seed_three(client)
    # Expire the newest one.
    from sqlalchemy import select

    from app.tv_context.models import TVContextItem

    async with core_db.SessionLocal() as session:
        row = (
            await session.execute(
                select(TVContextItem).where(TVContextItem.ticker == "NVDA")
            )
        ).scalars().first()
        row.status = STATUS_EXPIRED
        await session.commit()

    r = await client.get("/v1/tv-context/recent", headers=HEADERS)
    assert r.status_code == 200
    tickers = [it["ticker"] for it in r.json()]
    assert "NVDA" not in tickers
    assert tickers == ["MSFT", "AAPL"]


@pytest.mark.asyncio
async def test_recent_requires_auth(client):
    r = await client.get("/v1/tv-context/recent")
    assert r.status_code in (401, 403)
