"""Phase C1 — sync_outbox 7-day cleanup task."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.core import db as _db
from app.sync import service as sync_svc
from app.sync.models import SyncOutbox


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.asyncio
async def test_purge_removes_old_completed(client):
    old_completed = _now_utc() - datetime.timedelta(days=10)
    fresh_completed = _now_utc() - datetime.timedelta(days=2)

    async with _db.SessionLocal() as session:
        session.add(
            SyncOutbox(
                peer_url="http://peer", kind="ticker", symbol="AAPL",
                asset_class="stock", completed_at=old_completed,
            )
        )
        session.add(
            SyncOutbox(
                peer_url="http://peer", kind="ticker", symbol="MSFT",
                asset_class="stock", completed_at=fresh_completed,
            )
        )
        await session.commit()

    n = await sync_svc.purge_completed(retention_days=7)
    assert n == 1

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert len(rows) == 1
    assert rows[0].symbol == "MSFT"


@pytest.mark.asyncio
async def test_purge_never_touches_pending(client):
    async with _db.SessionLocal() as session:
        session.add(
            SyncOutbox(
                peer_url="http://peer", kind="ticker", symbol="AAPL",
                asset_class="stock", completed_at=None,
            )
        )
        await session.commit()

    n = await sync_svc.purge_completed(retention_days=0)
    # Even with retention=0, pending rows must survive.
    assert n == 0

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_purge_no_op_when_nothing_old(client):
    fresh = _now_utc() - datetime.timedelta(hours=1)
    async with _db.SessionLocal() as session:
        session.add(
            SyncOutbox(
                peer_url="http://peer", kind="ticker", symbol="AAPL",
                asset_class="stock", completed_at=fresh,
            )
        )
        await session.commit()

    n = await sync_svc.purge_completed(retention_days=7)
    assert n == 0
