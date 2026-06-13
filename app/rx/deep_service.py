"""rx deep-result store — read/write for out-of-band enrichment.

Sibling to ``app.rx.service``. Kept in its own module (high cohesion) because
the deep-result lifecycle is independent of the recommendation lifecycle: it
is written by a Claude Code session (ingest token) and read by the app
(API key), never mutated after insert.

See ``RxDeepResult`` model + ``.claude/plans/retrieval-depth-and-debiasing-program.md``
Phase 0 for the cost-seam rationale.
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from sqlalchemy import desc, select

from app.core import db as _db
from app.core.config import SETTINGS
from app.rx.models import RxDeepResult


def _ensure_aware(value: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    """SQLite drops tz; coerce naive datetimes back to UTC-aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


async def create(
    *,
    kind: str,
    rec_id: Optional[str] = None,
    query_hash: Optional[str] = None,
    payload: object,
    created_at: Optional[_dt.datetime] = None,
) -> RxDeepResult:
    """Insert a deep-result row. ``owner_user_id`` is server-side from env.

    Validation of ``kind`` and the rec_id/query_hash requirement is enforced
    by the Pydantic schema at the route boundary AND by the DB CHECK
    constraint on ``kind`` — this function trusts its callers but the DB is
    the last line of defence.
    """
    if not rec_id and not query_hash:
        raise ValueError("one of rec_id or query_hash is required")
    # Phase 8: deterministic governor decides banner/credibility from the
    # LLM's structured labels (alarm-fatigue + web-surface-bias guards).
    # Best-effort — a governor issue must never block enrichment ingest.
    governed_payload = payload
    try:
        from app.rx import deep_governors
        governed_payload = deep_governors.govern(kind, payload)
    except Exception as exc:  # noqa: BLE001
        import logging as _log
        _log.getLogger(__name__).warning(
            "rx.deep: governor failed for kind=%s: %s", kind, exc
        )
    row = RxDeepResult(
        owner_user_id=SETTINGS.RX_OPERATOR_UUID,
        rec_id=rec_id,
        query_hash=query_hash,
        kind=kind,
        payload=governed_payload,
    )
    if created_at is not None:
        row.created_at = _ensure_aware(created_at)
    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def list_for(
    *,
    rec_id: Optional[str] = None,
    query_hash: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
) -> List[RxDeepResult]:
    """List deep-results, newest first, scoped to the operator.

    Filters are AND-combined. At least one of ``rec_id`` / ``query_hash`` is
    expected in practice (the route enforces it) so a caller can't
    accidentally pull the whole table.
    """
    async with _db.SessionLocal() as session:
        stmt = select(RxDeepResult).where(
            RxDeepResult.owner_user_id == SETTINGS.RX_OPERATOR_UUID
        )
        if rec_id:
            stmt = stmt.where(RxDeepResult.rec_id == rec_id)
        if query_hash:
            stmt = stmt.where(RxDeepResult.query_hash == query_hash)
        if kind:
            stmt = stmt.where(RxDeepResult.kind == kind)
        stmt = stmt.order_by(desc(RxDeepResult.created_at)).limit(limit)
        result = await session.scalars(stmt)
        return list(result)
