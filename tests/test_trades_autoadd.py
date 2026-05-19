"""Auto-add ticker to a board on buy-trade log (2026-05-19).

Covers:
  * buy trade adds the ticker to the configured board
  * sell trade does NOT add
  * setting empty → no-op
  * board missing → no-op (logs but doesn't raise)
  * boards.add_ticker failure → trade still persists
  * idempotent — second buy of same ticker doesn't duplicate
"""
from __future__ import annotations

import pytest

from app.boards import service as boards_svc
from app.core.config import SETTINGS
from app.trades import service as trades_svc


HEADERS = {"X-API-Key": "test-key"}


async def _seed_positions_board(name: str = "positions") -> str:
    b = await boards_svc.create_board(name=name)
    return b["id"]


@pytest.mark.asyncio
async def test_buy_trade_autoadds_to_positions_board(client, monkeypatch):
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "positions")
    board_id = await _seed_positions_board()

    await trades_svc.create_trade(
        ticker="PLTR", side="buy", qty=10, entry_price=22.5
    )

    board = await boards_svc.get_board(board_id)
    tickers = [t["ticker"] for t in board["tickers"]]
    assert "PLTR" in tickers


@pytest.mark.asyncio
async def test_sell_trade_does_not_autoadd(client, monkeypatch):
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "positions")
    board_id = await _seed_positions_board()

    await trades_svc.create_trade(
        ticker="SHRT", side="sell", qty=5, entry_price=100.0
    )

    board = await boards_svc.get_board(board_id)
    tickers = [t["ticker"] for t in board["tickers"]]
    assert "SHRT" not in tickers


@pytest.mark.asyncio
async def test_empty_setting_disables_autoadd(client, monkeypatch):
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "")
    board_id = await _seed_positions_board()

    await trades_svc.create_trade(
        ticker="NVDA", side="buy", qty=3, entry_price=900.0
    )

    board = await boards_svc.get_board(board_id)
    tickers = [t["ticker"] for t in board["tickers"]]
    assert "NVDA" not in tickers


@pytest.mark.asyncio
async def test_missing_board_does_not_raise(client, monkeypatch):
    """Configured board name with no matching row → trade still writes."""
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "nonexistent")
    # No board seeded.

    t = await trades_svc.create_trade(
        ticker="META", side="buy", qty=2, entry_price=480.0
    )
    assert t["ticker"] == "META"


@pytest.mark.asyncio
async def test_boards_failure_does_not_block_trade(client, monkeypatch):
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "positions")
    await _seed_positions_board()

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated boards outage")

    monkeypatch.setattr(
        "app.boards.service.add_ticker", _boom
    )

    t = await trades_svc.create_trade(
        ticker="AAPL", side="buy", qty=1, entry_price=210.0
    )
    assert t["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_autoadd_is_idempotent(client, monkeypatch):
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "positions")
    board_id = await _seed_positions_board()

    await trades_svc.create_trade(
        ticker="TSLA", side="buy", qty=1, entry_price=300.0
    )
    await trades_svc.create_trade(
        ticker="TSLA", side="buy", qty=1, entry_price=305.0
    )

    board = await boards_svc.get_board(board_id)
    tsla_entries = [t for t in board["tickers"] if t["ticker"] == "TSLA"]
    assert len(tsla_entries) == 1


@pytest.mark.asyncio
async def test_board_name_lookup_case_insensitive(client, monkeypatch):
    monkeypatch.setattr(SETTINGS, "TRADES_AUTOADD_BOARD_NAME", "Positions")
    board_id = await _seed_positions_board(name="positions")

    await trades_svc.create_trade(
        ticker="MSFT", side="buy", qty=2, entry_price=420.0
    )

    board = await boards_svc.get_board(board_id)
    tickers = [t["ticker"] for t in board["tickers"]]
    assert "MSFT" in tickers
