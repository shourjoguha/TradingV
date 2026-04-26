"""Ticker labels CRUD.

Replication: every external CRUD enqueues a ``kind='label'`` outbox row so
the peer backend stays in sync. ``apply_imported_change`` writes directly
without enqueueing — used by ``POST /v1/labels/import`` to avoid loops.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import and_, delete, select

from app.core import db as _db
from app.labels.models import TickerLabel
from app.tickers import service as tickers_svc

logger = logging.getLogger(__name__)


async def _enqueue_replication(payload: dict[str, Any]) -> None:
    try:
        from app.sync import service as sync_svc

        await sync_svc.enqueue_kind("label", payload)
    except Exception:  # pragma: no cover - defensive
        logger.exception("labels: replication enqueue failed")


async def list_labels(symbol: str) -> list[TickerLabel]:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        rows = await session.execute(
            select(TickerLabel)
            .where(TickerLabel.symbol == sym)
            .order_by(TickerLabel.key)
        )
        return list(rows.scalars().all())


async def get_label(symbol: str, key: str) -> Optional[TickerLabel]:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        row = await session.execute(
            select(TickerLabel).where(
                and_(TickerLabel.symbol == sym, TickerLabel.key == key)
            )
        )
        return row.scalar_one_or_none()


async def upsert_label(symbol: str, key: str, value: Any) -> TickerLabel:
    """Idempotent: insert if missing, update value if present."""
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        # Auto-upsert ticker registry so a brand-new symbol can be labelled
        # without a separate POST /v1/tickers.
        await tickers_svc.upsert_ticker(session, sym, source="labels")

        existing = (
            await session.execute(
                select(TickerLabel).where(
                    and_(TickerLabel.symbol == sym, TickerLabel.key == key)
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.value = value
            await session.commit()
            await session.refresh(existing)
            await _enqueue_replication(
                {"action": "upsert", "symbol": sym, "key": key, "value": value}
            )
            return existing

        row = TickerLabel(symbol=sym, key=key, value=value)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    await _enqueue_replication(
        {"action": "upsert", "symbol": sym, "key": key, "value": value}
    )
    return row


async def bulk_upsert(symbol: str, labels: dict[str, Any]) -> list[TickerLabel]:
    """Upsert many keys in one transaction. Returns full label list after."""
    sym = tickers_svc.normalize(symbol)
    out: list[TickerLabel] = []
    async with _db.SessionLocal() as session:
        await tickers_svc.upsert_ticker(session, sym, source="labels")
        for key, value in labels.items():
            existing = (
                await session.execute(
                    select(TickerLabel).where(
                        and_(TickerLabel.symbol == sym, TickerLabel.key == key)
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.value = value
            else:
                session.add(TickerLabel(symbol=sym, key=key, value=value))
        await session.commit()

        rows = await session.execute(
            select(TickerLabel)
            .where(TickerLabel.symbol == sym)
            .order_by(TickerLabel.key)
        )
        out = list(rows.scalars().all())

    # Replicate each key as its own outbox row — keeps the receiver simple
    # (one upsert per row) and lets replication be partial-progress safe.
    for key, value in labels.items():
        await _enqueue_replication(
            {"action": "upsert", "symbol": sym, "key": key, "value": value}
        )
    return out


async def delete_label(symbol: str, key: str) -> bool:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        result = await session.execute(
            delete(TickerLabel).where(
                and_(TickerLabel.symbol == sym, TickerLabel.key == key)
            )
        )
        await session.commit()
        deleted = result.rowcount > 0
    if deleted:
        await _enqueue_replication(
            {"action": "delete", "symbol": sym, "key": key}
        )
    return deleted


async def apply_imported_change(payload: dict[str, Any]) -> str:
    """Apply a peer-pushed label change. Skips replication enqueue.

    Returns ``'upsert'`` | ``'delete'`` | ``'noop'``.
    """
    action = payload.get("action")
    symbol = payload.get("symbol")
    key = payload.get("key")
    if not action or not symbol or not key:
        return "noop"
    sym = tickers_svc.normalize(symbol)

    async with _db.SessionLocal() as session:
        if action == "delete":
            result = await session.execute(
                delete(TickerLabel).where(
                    and_(TickerLabel.symbol == sym, TickerLabel.key == key)
                )
            )
            await session.commit()
            return "delete" if result.rowcount > 0 else "noop"

        if action == "upsert":
            value = payload.get("value")
            await tickers_svc.upsert_ticker(session, sym, source="labels")
            existing = (
                await session.execute(
                    select(TickerLabel).where(
                        and_(TickerLabel.symbol == sym, TickerLabel.key == key)
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.value = value
            else:
                session.add(TickerLabel(symbol=sym, key=key, value=value))
            await session.commit()
            return "upsert"

    return "noop"


async def filter_symbols_by_labels(
    pairs: list[tuple[str, Any]]
) -> set[str]:
    """Return the set of symbols that match ALL (key, value) pairs.

    Used by watchlist/predictions endpoints to support
    ``?labels=sector:tech,capsize:large``-style filters.

    Comparison is exact-equality on the deserialised JSON value, decoded
    in Python rather than SQL — JSON-column equality is dialect-specific
    (Postgres works, SQLite stores quoted text). At v1 scale (≤40 tickers,
    handful of keys) the per-key scan is cheap and dialect-portable.
    """
    if not pairs:
        return set()
    matching: Optional[set[str]] = None
    async with _db.SessionLocal() as session:
        for key, expected in pairs:
            rows = await session.execute(
                select(TickerLabel.symbol, TickerLabel.value).where(
                    TickerLabel.key == key
                )
            )
            symbols = {sym for sym, val in rows.all() if val == expected}
            matching = symbols if matching is None else matching & symbols
            if not matching:
                return set()
    return matching or set()


def parse_labels_filter(spec: Optional[str]) -> list[tuple[str, Any]]:
    """Parse ``?labels=key:value,key2:value2`` into [(key, value), ...].

    Values are tried as JSON first (so ``insider_buy:true`` parses as
    bool), falling back to the literal string.
    """
    import json

    if not spec:
        return []
    out: list[tuple[str, Any]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if ":" not in chunk:
            continue
        key, _, raw = chunk.partition(":")
        key = key.strip()
        raw = raw.strip()
        if not key or not raw:
            continue
        try:
            val: Any = json.loads(raw)
        except (ValueError, TypeError):
            val = raw
        out.append((key, val))
    return out
