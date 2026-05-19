"""Boards service — Phase MW-2.

Owns CRUD for boards + board_tickers. Joins to ``ticker_market_data``
for quote data on read so the UI gets last_close + pct_1w in a single
trip. Auto-registers a ticker via the existing tickers registry on add
(same pattern as the watchlist module) so any new symbol shows up in
filters across the app.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.boards.models import Board, BoardTicker
from app.core import db as _db
from app.market_data.derived import TickerMarketData
from app.tickers import service as tickers_svc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRUD: boards
# ---------------------------------------------------------------------------

async def create_board(*, name: str, description: Optional[str] = None) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("name is required")
    async with _db.SessionLocal() as session:
        row = Board(name=name, description=description)
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise ValueError(f"board with name '{name}' already exists")
        await session.refresh(row)
    return _board_summary(row, ticker_count=0)


async def list_boards() -> list[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        boards_q = select(Board).order_by(Board.created_at.asc())
        boards = (await session.execute(boards_q)).scalars().all()
        # Single grouped count query — avoids N+1.
        count_q = (
            select(BoardTicker.board_id, func.count())
            .group_by(BoardTicker.board_id)
        )
        counts = dict((await session.execute(count_q)).all())
    return [_board_summary(b, ticker_count=int(counts.get(b.id, 0))) for b in boards]


async def get_board_id_by_name(name: str) -> Optional[str]:
    """Case-insensitive name lookup; returns board id or None.

    Cheap helper for fan-out integrations (e.g. auto-add on buy-trade
    log). Doesn't pre-fetch tickers — caller wants the id only.
    """
    if not name:
        return None
    target = name.strip().lower()
    if not target:
        return None
    async with _db.SessionLocal() as session:
        # SQLite has no LOWER() index but boards table is tiny (<50 rows)
        # so a full scan is fine. Postgres handles LOWER() in an index
        # scan if one exists; either way, this is bounded.
        row = (
            await session.execute(
                select(Board).where(func.lower(Board.name) == target)
            )
        ).scalar_one_or_none()
        return row.id if row else None


async def get_board(board_id: str) -> Optional[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        board = await session.get(Board, board_id)
        if board is None:
            return None
        # Tickers + quote data via outer-join on ticker_market_data.
        rows_q = (
            select(BoardTicker, TickerMarketData)
            .where(BoardTicker.board_id == board_id)
            .join(
                TickerMarketData,
                TickerMarketData.symbol == BoardTicker.ticker,
                isouter=True,
            )
            .order_by(BoardTicker.added_at.asc())
        )
        rows = (await session.execute(rows_q)).all()

    tickers = [
        {
            "ticker": bt.ticker,
            "notes": bt.notes,
            "added_at": bt.added_at,
            "last_close": float(tmd.last_close) if tmd is not None and tmd.last_close is not None else None,
            "last_close_at": tmd.last_close_at if tmd is not None else None,
            "pct_1w": float(tmd.pct_1w) if tmd is not None and tmd.pct_1w is not None else None,
            "quote_fetched_at": tmd.quote_fetched_at if tmd is not None else None,
        }
        for bt, tmd in rows
    ]
    summary = _board_summary(board, ticker_count=len(tickers))
    summary["tickers"] = tickers
    return summary


async def update_board(
    board_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with _db.SessionLocal() as session:
        board = await session.get(Board, board_id)
        if board is None:
            return None
        if name is not None:
            stripped = name.strip()
            if stripped:
                board.name = stripped
        if description is not None:
            board.description = description or None
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise ValueError("name conflicts with an existing board")
        await session.refresh(board)

        count = (
            await session.execute(
                select(func.count()).select_from(BoardTicker).where(BoardTicker.board_id == board_id)
            )
        ).scalar_one()
    return _board_summary(board, ticker_count=int(count))


async def delete_board(board_id: str) -> bool:
    async with _db.SessionLocal() as session:
        board = await session.get(Board, board_id)
        if board is None:
            return False
        await session.delete(board)
        await session.commit()
    return True


# ---------------------------------------------------------------------------
# CRUD: board_tickers
# ---------------------------------------------------------------------------

async def add_ticker(
    board_id: str,
    *,
    ticker: str,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Add a ticker to a board. Auto-registers the symbol via tickers
    registry (so it shows up in filters elsewhere). Idempotent on
    (board, ticker)."""
    sym = ticker.strip().upper()
    if not sym:
        raise ValueError("ticker is required")
    async with _db.SessionLocal() as session:
        board = await session.get(Board, board_id)
        if board is None:
            raise LookupError(f"board {board_id} not found")
        # Auto-register the symbol if new.
        await tickers_svc.upsert_ticker(session, sym, source="board")
        existing = await session.get(BoardTicker, (board_id, sym))
        if existing is None:
            session.add(BoardTicker(board_id=board_id, ticker=sym, notes=notes))
        elif notes is not None:
            existing.notes = notes
        await session.commit()
    return {"board_id": board_id, "ticker": sym, "notes": notes}


async def remove_ticker(board_id: str, ticker: str) -> bool:
    async with _db.SessionLocal() as session:
        existing = await session.get(BoardTicker, (board_id, ticker.upper()))
        if existing is None:
            return False
        await session.delete(existing)
        await session.commit()
    return True


async def move_ticker(
    *, ticker: str, source_board_id: str, target_board_id: str
) -> bool:
    """Atomic move: remove from source, add to target. Idempotent — if
    the ticker is already on target, the source row is removed and we
    return True."""
    sym = ticker.strip().upper()
    async with _db.SessionLocal() as session:
        target = await session.get(Board, target_board_id)
        if target is None:
            raise LookupError(f"target board {target_board_id} not found")
        src_row = await session.get(BoardTicker, (source_board_id, sym))
        if src_row is None:
            return False
        existing_target = await session.get(BoardTicker, (target_board_id, sym))
        if existing_target is None:
            await tickers_svc.upsert_ticker(session, sym, source="board")
            session.add(BoardTicker(board_id=target_board_id, ticker=sym, notes=src_row.notes))
        await session.delete(src_row)
        await session.commit()
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _board_summary(b: Board, *, ticker_count: int) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description,
        "ticker_count": ticker_count,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }
