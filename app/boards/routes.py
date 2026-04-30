"""Boards routes — Phase MW-2.

UI labels these "Watchlists"; backend keeps the ``boards`` name to
avoid collision with the existing operational ``watchlist`` table.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.boards import service
from app.boards.schemas import (
    BoardCreate,
    BoardDetail,
    BoardSummary,
    BoardUpdate,
    BoardsList,
    TickerAddRequest,
    TickerMoveRequest,
)
from app.core.auth import verify_api_key

router = APIRouter(prefix="/boards", tags=["boards"])


@router.get("", response_model=BoardsList)
async def list_boards(_api_key: str = Depends(verify_api_key)) -> BoardsList:
    items = await service.list_boards()
    return BoardsList(items=[BoardSummary(**b) for b in items])


@router.post("", response_model=BoardSummary, status_code=201)
async def create_board(
    body: BoardCreate, _api_key: str = Depends(verify_api_key)
) -> BoardSummary:
    try:
        b = await service.create_board(name=body.name, description=body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BoardSummary(**b)


@router.get("/{board_id}", response_model=BoardDetail)
async def get_board(
    board_id: str, _api_key: str = Depends(verify_api_key)
) -> BoardDetail:
    b = await service.get_board(board_id)
    if b is None:
        raise HTTPException(status_code=404, detail="board not found")
    return BoardDetail(**b)


@router.patch("/{board_id}", response_model=BoardSummary)
async def update_board(
    board_id: str,
    body: BoardUpdate,
    _api_key: str = Depends(verify_api_key),
) -> BoardSummary:
    try:
        b = await service.update_board(
            board_id, name=body.name, description=body.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if b is None:
        raise HTTPException(status_code=404, detail="board not found")
    return BoardSummary(**b)


@router.delete("/{board_id}", status_code=204)
async def delete_board(
    board_id: str, _api_key: str = Depends(verify_api_key)
) -> None:
    ok = await service.delete_board(board_id)
    if not ok:
        raise HTTPException(status_code=404, detail="board not found")
    return None


@router.post("/{board_id}/tickers", status_code=201)
async def add_ticker(
    board_id: str,
    body: TickerAddRequest,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    try:
        return await service.add_ticker(board_id, ticker=body.ticker, notes=body.notes)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{board_id}/tickers/{ticker}", status_code=204)
async def remove_ticker(
    board_id: str,
    ticker: str,
    _api_key: str = Depends(verify_api_key),
) -> None:
    ok = await service.remove_ticker(board_id, ticker)
    if not ok:
        raise HTTPException(status_code=404, detail="ticker not on board")
    return None


@router.post("/{board_id}/tickers/move")
async def move_ticker(
    board_id: str,
    body: TickerMoveRequest,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, bool]:
    """Move a ticker from `board_id` to `body.target_board_id`."""
    try:
        ok = await service.move_ticker(
            ticker=body.ticker,
            source_board_id=board_id,
            target_board_id=body.target_board_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="ticker not on source board")
    return {"moved": True}
