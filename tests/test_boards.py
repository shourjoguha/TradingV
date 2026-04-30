"""Boards CRUD + ticker move + quote-data join — Phase MW-2."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.boards import service as boards_service
from app.boards.models import Board, BoardTicker
from app.core import db as _db

HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Service: CRUD on boards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_board_persists_with_unique_name(client):
    a = await boards_service.create_board(name="Reshoring plays")
    assert a["name"] == "Reshoring plays"
    assert a["ticker_count"] == 0

    with pytest.raises(ValueError, match="already exists"):
        await boards_service.create_board(name="Reshoring plays")


@pytest.mark.asyncio
async def test_list_boards_returns_ticker_counts(client):
    a = await boards_service.create_board(name="A")
    b = await boards_service.create_board(name="B")
    await boards_service.add_ticker(a["id"], ticker="aapl")
    await boards_service.add_ticker(a["id"], ticker="msft")
    await boards_service.add_ticker(b["id"], ticker="goog")

    boards = await boards_service.list_boards()
    counts = {b["name"]: b["ticker_count"] for b in boards}
    assert counts == {"A": 2, "B": 1}


@pytest.mark.asyncio
async def test_get_board_includes_tickers_with_quote_data(client):
    """Verify the outer-join to ticker_market_data — quote columns surface
    even when no quote row exists yet (NULLs)."""
    b = await boards_service.create_board(name="X")
    await boards_service.add_ticker(b["id"], ticker="AAPL", notes="checking")

    detail = await boards_service.get_board(b["id"])
    assert detail is not None
    assert detail["ticker_count"] == 1
    assert detail["tickers"][0]["ticker"] == "AAPL"
    assert detail["tickers"][0]["notes"] == "checking"
    # Quote data not yet fetched — should be None across the board.
    assert detail["tickers"][0]["last_close"] is None
    assert detail["tickers"][0]["pct_1w"] is None


@pytest.mark.asyncio
async def test_get_board_quote_data_surfaces_when_present(client):
    """Manually insert a TickerMarketData row; verify it joins through."""
    from app.market_data.derived import TickerMarketData

    b = await boards_service.create_board(name="Y")
    await boards_service.add_ticker(b["id"], ticker="AAPL")

    async with _db.SessionLocal() as s:
        s.add(
            TickerMarketData(
                symbol="AAPL",
                fetched_at=datetime.datetime.now(datetime.timezone.utc),
                last_close=189.50,
                last_close_at=datetime.date(2026, 4, 30),
                pct_1w=2.5,
                quote_fetched_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await s.commit()

    detail = await boards_service.get_board(b["id"])
    t = detail["tickers"][0]
    assert t["last_close"] == 189.50
    assert t["pct_1w"] == 2.5
    assert t["last_close_at"] == datetime.date(2026, 4, 30)


# ---------------------------------------------------------------------------
# Service: tickers on boards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_ticker_idempotent_on_repeat(client):
    b = await boards_service.create_board(name="Z")
    await boards_service.add_ticker(b["id"], ticker="aapl", notes="first")
    await boards_service.add_ticker(b["id"], ticker="aapl", notes="updated")

    async with _db.SessionLocal() as s:
        rows = (await s.execute(select(BoardTicker))).scalars().all()
    assert len(rows) == 1
    assert rows[0].notes == "updated"
    assert rows[0].ticker == "AAPL"  # auto-uppercased


@pytest.mark.asyncio
async def test_add_ticker_unknown_board_raises(client):
    with pytest.raises(LookupError):
        await boards_service.add_ticker("00000000-0000-0000-0000-000000000000", ticker="AAPL")


@pytest.mark.asyncio
async def test_remove_ticker(client):
    b = await boards_service.create_board(name="Q")
    await boards_service.add_ticker(b["id"], ticker="AAPL")
    ok = await boards_service.remove_ticker(b["id"], "aapl")
    assert ok is True
    detail = await boards_service.get_board(b["id"])
    assert detail["tickers"] == []


@pytest.mark.asyncio
async def test_move_ticker_across_boards(client):
    a = await boards_service.create_board(name="Source")
    b = await boards_service.create_board(name="Target")
    await boards_service.add_ticker(a["id"], ticker="AAPL", notes="initial")

    ok = await boards_service.move_ticker(
        ticker="AAPL", source_board_id=a["id"], target_board_id=b["id"]
    )
    assert ok is True

    src = await boards_service.get_board(a["id"])
    tgt = await boards_service.get_board(b["id"])
    assert src["tickers"] == []
    assert len(tgt["tickers"]) == 1
    assert tgt["tickers"][0]["ticker"] == "AAPL"
    assert tgt["tickers"][0]["notes"] == "initial"


@pytest.mark.asyncio
async def test_move_ticker_when_already_on_target_just_removes_source(client):
    a = await boards_service.create_board(name="Src")
    b = await boards_service.create_board(name="Tgt")
    await boards_service.add_ticker(a["id"], ticker="AAPL", notes="src-note")
    await boards_service.add_ticker(b["id"], ticker="AAPL", notes="tgt-note")

    ok = await boards_service.move_ticker(
        ticker="AAPL", source_board_id=a["id"], target_board_id=b["id"]
    )
    assert ok is True

    src = await boards_service.get_board(a["id"])
    tgt = await boards_service.get_board(b["id"])
    assert src["tickers"] == []
    # Target keeps its existing notes (we didn't overwrite).
    assert tgt["tickers"][0]["notes"] == "tgt-note"


@pytest.mark.asyncio
async def test_delete_board_cascades_to_tickers(client):
    b = await boards_service.create_board(name="ToDelete")
    await boards_service.add_ticker(b["id"], ticker="AAPL")
    await boards_service.add_ticker(b["id"], ticker="MSFT")

    ok = await boards_service.delete_board(b["id"])
    assert ok is True

    async with _db.SessionLocal() as s:
        boards_left = (await s.execute(select(Board))).scalars().all()
        bt_left = (await s.execute(select(BoardTicker))).scalars().all()
    assert boards_left == []
    assert bt_left == []


# ---------------------------------------------------------------------------
# Routes — JSON contract round-trips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_create_then_list(client):
    r = await client.post(
        "/v1/boards", headers=HEADERS, json={"name": "Costa-mentioned"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Costa-mentioned"
    assert body["ticker_count"] == 0

    r2 = await client.get("/v1/boards", headers=HEADERS)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Costa-mentioned"


@pytest.mark.asyncio
async def test_route_add_ticker_and_get(client):
    create = await client.post(
        "/v1/boards", headers=HEADERS, json={"name": "AI-resilient SaaS"}
    )
    bid = create.json()["id"]

    add = await client.post(
        f"/v1/boards/{bid}/tickers", headers=HEADERS,
        json={"ticker": "okta", "notes": "mission-critical thesis"},
    )
    assert add.status_code == 201

    detail = await client.get(f"/v1/boards/{bid}", headers=HEADERS)
    assert detail.status_code == 200
    body = detail.json()
    assert body["ticker_count"] == 1
    assert body["tickers"][0]["ticker"] == "OKTA"
    assert body["tickers"][0]["notes"] == "mission-critical thesis"


@pytest.mark.asyncio
async def test_route_delete_board(client):
    create = await client.post("/v1/boards", headers=HEADERS, json={"name": "Trash"})
    bid = create.json()["id"]
    r = await client.delete(f"/v1/boards/{bid}", headers=HEADERS)
    assert r.status_code == 204
    r2 = await client.get(f"/v1/boards/{bid}", headers=HEADERS)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_route_move_ticker_endpoint(client):
    a = (await client.post("/v1/boards", headers=HEADERS, json={"name": "A"})).json()
    b = (await client.post("/v1/boards", headers=HEADERS, json={"name": "B"})).json()
    await client.post(
        f"/v1/boards/{a['id']}/tickers", headers=HEADERS, json={"ticker": "MSFT"}
    )

    r = await client.post(
        f"/v1/boards/{a['id']}/tickers/move",
        headers=HEADERS,
        json={"ticker": "MSFT", "target_board_id": b["id"]},
    )
    assert r.status_code == 200
    assert r.json() == {"moved": True}


@pytest.mark.asyncio
async def test_route_create_requires_auth(client):
    r = await client.post("/v1/boards", json={"name": "no-auth"})
    assert r.status_code in (401, 403)
