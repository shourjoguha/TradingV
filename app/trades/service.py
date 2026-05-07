"""Trade journal CRUD + simple P&L summary — Phase 5."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from sqlalchemy import func, select

from app.core import db as _db
from app.opportunities.models import Opportunity
from app.trades.models import Trade

logger = logging.getLogger(__name__)


def _compute_pnl(side: str, qty: float, entry: float, exit_p: Optional[float], fees: float) -> Optional[float]:
    if exit_p is None:
        return None
    delta = (exit_p - entry) if side == "buy" else (entry - exit_p)
    return delta * qty - fees


def _serialize(t: Trade) -> dict[str, Any]:
    return {
        "id": t.id,
        "opportunity_id": t.opportunity_id,
        "ticker": t.ticker,
        "side": t.side,
        "qty": t.qty,
        "entry_price": t.entry_price,
        "entry_at": t.entry_at.isoformat(),
        "exit_price": t.exit_price,
        "exit_at": t.exit_at.isoformat() if t.exit_at else None,
        "realized_pnl": t.realized_pnl,
        "fees": t.fees,
        "notes_md": t.notes_md,
        "created_at": t.created_at.isoformat(),
    }


async def create_trade(
    *,
    ticker: str,
    side: str,
    qty: float,
    entry_price: float,
    entry_at: Optional[datetime.datetime] = None,
    opportunity_id: Optional[str] = None,
    fees: float = 0.0,
    notes_md: Optional[str] = None,
) -> dict[str, Any]:
    if side not in ("buy", "sell"):
        raise ValueError(f"invalid side: {side}")
    entry_at = entry_at or datetime.datetime.now(datetime.timezone.utc)
    async with _db.SessionLocal() as session:
        if opportunity_id:
            opp = await session.get(Opportunity, opportunity_id)
            if opp is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")
        t = Trade(
            opportunity_id=opportunity_id,
            ticker=ticker.upper(),
            side=side,
            qty=qty,
            entry_price=entry_price,
            entry_at=entry_at,
            fees=fees,
            notes_md=notes_md,
        )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return _serialize(t)


async def update_trade(
    trade_id: str,
    *,
    exit_price: Optional[float] = None,
    exit_at: Optional[datetime.datetime] = None,
    fees: Optional[float] = None,
    notes_md: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        t = await session.get(Trade, trade_id)
        if t is None:
            return None
        was_closed_before = t.exit_price is not None
        if exit_price is not None:
            t.exit_price = exit_price
        if exit_at is not None:
            t.exit_at = exit_at
        if fees is not None:
            t.fees = fees
        if notes_md is not None:
            t.notes_md = notes_md
        # Recompute realized_pnl if we have an exit.
        if t.exit_price is not None:
            t.realized_pnl = _compute_pnl(t.side, t.qty, t.entry_price, t.exit_price, t.fees)
        await session.commit()
        await session.refresh(t)

        # TV-context enrichment hook: when this PATCH is the one that
        # closes the trade (open → closed transition), walk recent
        # tv_context_items in entry_at±24h and stamp tombstones with the
        # outcome. Idempotent (re-PATCH on already-closed trades is a
        # no-op via tombstone.trades dedupe inside the helper). Failures
        # are logged but never block the trade-close response.
        if t.exit_price is not None and not was_closed_before:
            await _enrich_tv_context(t)

        return _serialize(t)


async def _enrich_tv_context(t: Trade) -> None:
    """Best-effort fan-out to ``tv_context.enrich_on_trade_close``.

    Runs in a fresh session to avoid commit-ordering bugs with the
    update_trade transaction. Mirrors the alerts → tv_context fan-out
    pattern: never raise; log on failure.
    """
    try:
        from app.tv_context import service as _tvc_service

        exit_at = t.exit_at or datetime.datetime.now(datetime.timezone.utc)
        async with _db.SessionLocal() as session:
            await _tvc_service.enrich_on_trade_close(
                session=session,
                trade_id=t.id,
                ticker=t.ticker,
                entry_at=t.entry_at,
                exit_at=exit_at,
                realized_pnl=t.realized_pnl,
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "trades: tv_context enrichment failed for trade %s", t.id, exc_info=True
        )


async def list_trades(
    *,
    ticker: Optional[str] = None,
    opportunity_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        stmt = select(Trade).order_by(Trade.entry_at.desc()).limit(limit)
        if ticker:
            stmt = stmt.where(Trade.ticker == ticker.upper())
        if opportunity_id:
            stmt = stmt.where(Trade.opportunity_id == opportunity_id)
        rows = (await session.execute(stmt)).scalars().all()
        return [_serialize(r) for r in rows]


async def pnl_summary() -> dict[str, Any]:
    """Aggregate realized P&L by closed trades. Open trades not counted."""
    async with _db.SessionLocal() as session:
        stmt = select(
            func.count(Trade.id).filter(Trade.exit_price.is_not(None)).label("closed_n"),
            func.count(Trade.id).filter(Trade.exit_price.is_(None)).label("open_n"),
            func.coalesce(func.sum(Trade.realized_pnl), 0.0).label("total_pnl"),
        )
        row = (await session.execute(stmt)).one()
        return {
            "closed_count": int(row.closed_n or 0),
            "open_count": int(row.open_n or 0),
            "total_realized_pnl": float(row.total_pnl or 0.0),
        }


async def pnl_by_rule() -> list[dict[str, Any]]:
    """Per-rule P&L attribution: 'what if I'd taken every R1 signal?'.

    Joins trades → opportunities → rule_id, rolls up realized_pnl per rule.
    Only counts trades linked to opportunities and with exits.
    """
    async with _db.SessionLocal() as session:
        stmt = (
            select(
                Opportunity.rule_id,
                Opportunity.rule_label,
                func.count(Trade.id).label("trade_count"),
                func.coalesce(func.sum(Trade.realized_pnl), 0.0).label("total_pnl"),
                func.coalesce(func.avg(Trade.realized_pnl), 0.0).label("avg_pnl"),
            )
            .join(Opportunity, Trade.opportunity_id == Opportunity.id)
            .where(Trade.exit_price.is_not(None))
            .group_by(Opportunity.rule_id, Opportunity.rule_label)
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                "rule_id": r.rule_id,
                "rule_label": r.rule_label,
                "trade_count": int(r.trade_count),
                "total_pnl": float(r.total_pnl),
                "avg_pnl": float(r.avg_pnl),
            }
            for r in rows
        ]
