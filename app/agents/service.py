"""Agents lane service — run the multi-agent engine, persist decisions.

- :func:`run_for_ticker` — one ticker, one decision, idempotent upsert.
- :func:`run_for_watchlist` — iterate the existing watchlist roster.
- :func:`list_decisions` — read back recent decisions.

Deliberately NO bridge into the shared ``opportunities`` feed: that table is
FK-bound to Kronos' ``prediction_points`` (NOT NULL), so an agent decision has
no valid row to point at. Keeping the agent lane in its own ``agent_decisions``
table + ``/v1/agents/decisions`` surface honors the operator's "side-by-side,
need not talk to each other" constraint without mutating the Kronos schema.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents.adapter import get_engine
from app.agents.models import AgentDecisionRow
from app.core import db as _db

logger = logging.getLogger(__name__)


async def run_for_ticker(
    ticker: str, *, made_on: Optional[datetime.date] = None
) -> dict:
    """Run the active engine for one ticker and persist the decision.

    Idempotent on (ticker, made_on, engine_version): a second run on the same
    day returns the existing row rather than inserting a duplicate.
    """
    made_on = made_on or datetime.datetime.now(datetime.timezone.utc).date()
    engine = get_engine()
    decision = await engine.decide(ticker.upper(), made_on=made_on)

    async with _db.SessionLocal() as session:
        row = AgentDecisionRow(
            ticker=decision.ticker,
            made_on=decision.made_on,
            engine=decision.engine,
            engine_version=decision.engine_version,
            stance=decision.stance,
            confidence=decision.confidence,
            rationale_md=decision.rationale_md,
            transcript_ref=decision.transcript_ref,
            meta=decision.meta or None,
        )
        session.add(row)
        try:
            await session.flush()
            created = True
        except IntegrityError:
            await session.rollback()
            created = False
            existing = (
                await session.execute(
                    select(AgentDecisionRow).where(
                        AgentDecisionRow.ticker == decision.ticker,
                        AgentDecisionRow.made_on == decision.made_on,
                        AgentDecisionRow.engine_version == decision.engine_version,
                    )
                )
            ).scalars().first()
            row = existing if existing is not None else row

        await session.commit()
        return {"created": created, **_serialize(row)}


async def run_for_watchlist(
    *, made_on: Optional[datetime.date] = None, limit: int = 1000
) -> dict[str, int]:
    """Run the engine across the watchlist roster. Best-effort per ticker."""
    from app.watchlist.models import WatchlistEntry

    made_on = made_on or datetime.datetime.now(datetime.timezone.utc).date()
    stats = {"scanned": 0, "created": 0, "existing": 0, "failed": 0}

    async with _db.SessionLocal() as session:
        symbols = (
            await session.execute(
                select(WatchlistEntry.symbol).order_by(WatchlistEntry.symbol).limit(limit)
            )
        ).scalars().all()

    stats["scanned"] = len(symbols)
    for sym in symbols:
        try:
            res = await run_for_ticker(sym, made_on=made_on)
            stats["created" if res.get("created") else "existing"] += 1
        except Exception as e:  # noqa: BLE001 — one bad ticker shouldn't stop the roster
            logger.warning("agents: decision failed for %s: %s", sym, e)
            stats["failed"] += 1
    return stats


async def list_decisions(
    *, ticker: Optional[str] = None, stance: Optional[str] = None, limit: int = 100
) -> list[dict]:
    async with _db.SessionLocal() as session:
        stmt = (
            select(AgentDecisionRow)
            .order_by(AgentDecisionRow.made_on.desc(), AgentDecisionRow.created_at.desc())
            .limit(limit)
        )
        if ticker:
            stmt = stmt.where(AgentDecisionRow.ticker == ticker.upper())
        if stance:
            stmt = stmt.where(AgentDecisionRow.stance == stance.upper())
        rows = (await session.execute(stmt)).scalars().all()
        return [_serialize(r) for r in rows]


def _serialize(r: AgentDecisionRow) -> dict:
    return {
        "id": r.id,
        "ticker": r.ticker,
        "made_on": r.made_on.isoformat() if r.made_on else None,
        "engine": r.engine,
        "engine_version": r.engine_version,
        "stance": r.stance,
        "confidence": r.confidence,
        "rationale_md": r.rationale_md,
        "transcript_ref": r.transcript_ref,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
