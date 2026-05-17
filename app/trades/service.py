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
        "related_rec_id": t.related_rec_id,
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
    related_rec_id: Optional[str] = None,
) -> dict[str, Any]:
    if side not in ("buy", "sell"):
        raise ValueError(f"invalid side: {side}")
    entry_at = entry_at or datetime.datetime.now(datetime.timezone.utc)
    async with _db.SessionLocal() as session:
        if opportunity_id:
            opp = await session.get(Opportunity, opportunity_id)
            if opp is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")
        # rx v1.x.1-b: validate the linked rec actually exists + is finance
        # before stamping the FK. Database CHECK already enforces domain on
        # the rec itself, but validating here gives a useful 400 instead of
        # a referential-integrity error.
        if related_rec_id:
            from app.rx.models import Recommendation
            rec = await session.get(Recommendation, related_rec_id)
            if rec is None:
                raise ValueError(f"rec not found: {related_rec_id}")
            if rec.domain != "finance":
                raise ValueError("related_rec_id must reference a finance rec")
        t = Trade(
            opportunity_id=opportunity_id,
            ticker=ticker.upper(),
            side=side,
            qty=qty,
            entry_price=entry_price,
            entry_at=entry_at,
            fees=fees,
            notes_md=notes_md,
            related_rec_id=related_rec_id,
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


# ---------------------------------------------------------------------------
# Position aggregation (rx v1.x.1-b)
# ---------------------------------------------------------------------------

# Risk-rule thresholds. Source-of-truth lives in
# `~/Documents/Sho's Playgroun/Lakshmi/01_rules/risk_rules.md` (operator
# vault — not in this repo). Hardcoded here for speed; if rules drift,
# update both surfaces. Sector concentration is intentionally NOT computed
# (no sector lookup table in TradingV — flagged for v1.x.1-c).
RISK_SINGLE_POSITION_THRESHOLD = 0.05  # >5% of portfolio in one ticker
RISK_SECTOR_THRESHOLD = 0.50  # >50% in one sector — placeholder, not enforced

# Don't fire the single-position flag when the portfolio is too small for
# concentration risk to matter. Two open trades of equal size will always
# show 50% concentration; the flag becomes noise until the operator has
# real diversification at stake. ~$5k is the threshold at which a single
# >5% position becomes a meaningfully sized bet.
RISK_FLAG_MIN_PORTFOLIO = 5000.0
# And don't fire when there are fewer than this many distinct positions —
# concentration is mechanical, not a real risk signal, when the count is
# below this floor.
RISK_FLAG_MIN_POSITIONS = 4


async def list_positions(*, limit: int = 200) -> dict[str, Any]:
    """Aggregate open trades into per-ticker positions.

    Open = exit_price IS NULL. Long-only assumption for now: side='buy'
    contributes qty, side='sell' contributes -qty (interpreted as a
    short). avg_price weighted by signed qty for open lots only.
    current_value uses latest OHLCV close for the ticker; falls back to
    entry_price when no quote is available (laptop's market_data path
    keeps OHLCV fresh on the daily schedule).

    Risk flags:
      * `single_position` — abs(value) / portfolio_total > 0.05
      * `sector` — placeholder; always [] (no sector table)
    """
    from sqlalchemy import select
    from app.market_data.models import OhlcvBar

    async with _db.SessionLocal() as session:
        # Pull open trades once. Hard cap of 2000 rows protects against
        # pathological inputs (single user app — realistic open-trade count
        # is well under 100; 2000 is 20x buffer, not 20x limit).
        rows = list(
            await session.scalars(
                select(Trade)
                .where(Trade.exit_price.is_(None))
                .limit(2000)
            )
        )
        tickers = sorted({t.ticker.upper() for t in rows})
        latest_close: dict[str, float] = {}
        if tickers:
            # Single grouped query for daily closes per ticker. Avoids
            # N+1 round-trips: previous loop issued up to 2 queries per
            # ticker; this is one ResultSet covering the whole basket.
            # Sub-select picks the most-recent ts per symbol; outer join
            # back to OhlcvBar fetches the close at that ts. Works on
            # both Postgres and SQLite (no DISTINCT ON dependency).
            from sqlalchemy import func as _sqlfunc, and_

            sub = (
                select(
                    OhlcvBar.symbol.label("sym"),
                    _sqlfunc.max(OhlcvBar.ts).label("max_ts"),
                )
                .where(
                    OhlcvBar.symbol.in_(tickers),
                    OhlcvBar.interval == "1d",
                )
                .group_by(OhlcvBar.symbol)
                .subquery()
            )
            stmt = select(OhlcvBar.symbol, OhlcvBar.close).join(
                sub,
                and_(
                    OhlcvBar.symbol == sub.c.sym,
                    OhlcvBar.ts == sub.c.max_ts,
                    OhlcvBar.interval == "1d",
                ),
            )
            for sym, close in (await session.execute(stmt)).all():
                latest_close[sym] = float(close)
            # Fallback for tickers w/o 1d bars: any-interval latest close.
            missing = [s for s in tickers if s not in latest_close]
            if missing:
                sub2 = (
                    select(
                        OhlcvBar.symbol.label("sym"),
                        _sqlfunc.max(OhlcvBar.ts).label("max_ts"),
                    )
                    .where(OhlcvBar.symbol.in_(missing))
                    .group_by(OhlcvBar.symbol)
                    .subquery()
                )
                stmt2 = select(OhlcvBar.symbol, OhlcvBar.close).join(
                    sub2,
                    and_(
                        OhlcvBar.symbol == sub2.c.sym,
                        OhlcvBar.ts == sub2.c.max_ts,
                    ),
                )
                for sym, close in (await session.execute(stmt2)).all():
                    latest_close[sym] = float(close)

        # Materialize Trade rows into plain dicts BEFORE session close so
        # subsequent attribute reads don't lazy-load on detached instances
        # (SQLAlchemy async raises MissingGreenlet on detached access).
        trade_dicts = [
            {
                "id": t.id,
                "ticker": t.ticker.upper(),
                "side": t.side,
                "qty": t.qty or 0.0,
                "entry_price": t.entry_price or 0.0,
                "related_rec_id": t.related_rec_id,
            }
            for t in rows
        ]

    positions: dict[str, dict[str, Any]] = {}
    for t in trade_dicts:
        sym = t["ticker"]
        signed_qty = t["qty"] if t["side"] == "buy" else -t["qty"]
        p = positions.setdefault(
            sym,
            {
                "ticker": sym,
                "qty": 0.0,
                "cost_basis": 0.0,
                "current_price": latest_close.get(sym),
                "trade_ids": [],
                "has_rec_link": False,
            },
        )
        p["qty"] += signed_qty
        # Cost basis sums signed cash outlay (buy cash out, sell cash in).
        p["cost_basis"] += signed_qty * t["entry_price"]
        p["trade_ids"].append(t["id"])
        if t["related_rec_id"]:
            p["has_rec_link"] = True

    # Compute derived fields.
    out_items: list[dict[str, Any]] = []
    portfolio_total = 0.0
    for sym, p in positions.items():
        avg_price = None
        if p["qty"] != 0:
            avg_price = abs(p["cost_basis"] / p["qty"])
        px = p.get("current_price") or avg_price or 0.0
        current_value = px * abs(p["qty"]) if p["qty"] else 0.0
        portfolio_total += current_value
        p["avg_price"] = avg_price
        p["current_value"] = current_value
        out_items.append(p)
    # Concentration risk: gate on portfolio scale + count of positions
    # so the flag means something rather than firing trivially on every
    # row when the operator has 2 positions of any size.
    risk_eligible = (
        portfolio_total >= RISK_FLAG_MIN_PORTFOLIO
        and len(out_items) >= RISK_FLAG_MIN_POSITIONS
    )
    for p in out_items:
        p["pct_portfolio"] = (
            (p["current_value"] / portfolio_total) if portfolio_total > 0 else 0.0
        )
        # Unrealized P&L vs cost basis. cost_basis already accounts for
        # signed_qty so long positions show positive on price appreciation,
        # shorts the opposite. Percentage normalises against absolute cost
        # basis to keep direction intuitive for the operator.
        cost = p.get("cost_basis") or 0.0
        if p["qty"] != 0 and cost != 0:
            p["unrealized_pnl"] = p["current_value"] - abs(cost)
            p["unrealized_pnl_pct"] = (
                p["unrealized_pnl"] / abs(cost) if abs(cost) > 0 else None
            )
        else:
            p["unrealized_pnl"] = 0.0
            p["unrealized_pnl_pct"] = None
        p["risk_flag_single"] = bool(
            risk_eligible
            and p["pct_portfolio"] > RISK_SINGLE_POSITION_THRESHOLD
        )
        # Sector flag deferred — no sector data in TradingV (v1.x.1-c).
        p["risk_flag_sector"] = False
    out_items.sort(key=lambda x: x["current_value"], reverse=True)
    # Aggregate unrealized P&L across the book — a useful sticky number
    # for the portfolio header card.
    total_unrealized = sum(
        (p.get("unrealized_pnl") or 0.0) for p in out_items
    )
    return {
        "items": out_items[:limit],
        "portfolio_total_value": portfolio_total,
        "portfolio_unrealized_pnl": total_unrealized,
        "count": len(out_items),
    }
