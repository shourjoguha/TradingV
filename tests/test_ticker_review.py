"""Ticker review queue — Phase D.

Covers:
  * enqueue_or_bump idempotency + cap behaviour
  * list_pending min_seen filter
  * resolve chains to watchlist / boards atomically
  * weekly_digest_md format + sentinel block
  * re-eligibility window — dismissed row resurfaces after 90d
"""
from __future__ import annotations

import datetime as _dt

import pytest

from app.boards import service as boards_service
from app.core import db as _db
from app.ticker_review import service
from app.ticker_review.models import TickerReviewEntry
from app.watchlist import service as watchlist_service

HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Service: enqueue_or_bump
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_creates_new_row(client):
    row = await service.enqueue_or_bump(
        ticker="pltr",
        video_id="vid-1",
        channel="click-capital",
        snippet="Palantir 1D chart",
    )
    assert row is not None
    assert row.ticker == "PLTR"
    assert row.times_seen == 1
    assert row.channels == ["click-capital"]
    assert row.recent_video_ids == ["vid-1"]
    assert row.recent_caption_snippets == ["Palantir 1D chart"]
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_enqueue_bumps_existing(client):
    await service.enqueue_or_bump(
        ticker="PLTR", video_id="v1", channel="click-capital", snippet="s1"
    )
    row = await service.enqueue_or_bump(
        ticker="PLTR", video_id="v2", channel="fx-evolution", snippet="s2"
    )
    assert row.times_seen == 2
    assert set(row.channels) == {"click-capital", "fx-evolution"}
    assert "v1" in row.recent_video_ids and "v2" in row.recent_video_ids


@pytest.mark.asyncio
async def test_enqueue_caps_lists_at_three(client):
    for i in range(5):
        await service.enqueue_or_bump(
            ticker="ASTS",
            video_id=f"v{i}",
            channel=f"chan-{i}",
            snippet=f"snippet-{i}",
        )
    async with _db.SessionLocal() as session:
        row = await session.scalar(
            __import__("sqlalchemy").select(TickerReviewEntry).where(
                TickerReviewEntry.ticker == "ASTS"
            )
        )
    assert row.times_seen == 5
    assert len(row.recent_video_ids) == 3
    assert len(row.channels) == 3
    assert len(row.recent_caption_snippets) == 3
    # Most-recent-last ordering preserved.
    assert row.recent_video_ids[-1] == "v4"


@pytest.mark.asyncio
async def test_enqueue_rejects_empty_ticker(client):
    assert await service.enqueue_or_bump(
        ticker="", video_id="v", channel="c", snippet="s"
    ) is None
    assert await service.enqueue_or_bump(
        ticker="   ", video_id="v", channel="c", snippet="s"
    ) is None


# ---------------------------------------------------------------------------
# Service: list_pending min_seen filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_filters_by_min_seen(client):
    # One mention — below threshold.
    await service.enqueue_or_bump(
        ticker="ONCE", video_id="v1", channel="c", snippet="x"
    )
    # Two mentions — surfaces.
    await service.enqueue_or_bump(
        ticker="TWICE", video_id="v1", channel="c", snippet="x"
    )
    await service.enqueue_or_bump(
        ticker="TWICE", video_id="v2", channel="c", snippet="y"
    )
    rows = await service.list_pending()
    tickers = {r.ticker for r in rows}
    assert "TWICE" in tickers
    assert "ONCE" not in tickers


# ---------------------------------------------------------------------------
# Service: resolve chains atomically
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_add_to_roster_persists_watchlist(client):
    row = await service.enqueue_or_bump(
        ticker="PLTR", video_id="v1", channel="c", snippet="s"
    )
    resolved = await service.resolve(row.id, action="add_to_roster")
    assert resolved.status == "added_to_roster"
    assert resolved.resolved_at is not None
    wl = await watchlist_service.get_entry("PLTR")
    assert wl is not None


@pytest.mark.asyncio
async def test_resolve_add_to_board_persists(client):
    b = await boards_service.create_board(name="High conviction")
    row = await service.enqueue_or_bump(
        ticker="ASTS", video_id="v1", channel="c", snippet="s"
    )
    resolved = await service.resolve(
        row.id, action="add_to_board", board_id=b["id"]
    )
    assert resolved.status == "added_to_board"
    assert resolved.resolved_target == b["id"]
    detail = await boards_service.get_board(b["id"])
    tickers = [t["ticker"] for t in detail["tickers"]]
    assert "ASTS" in tickers


@pytest.mark.asyncio
async def test_resolve_dismiss_marks_status(client):
    row = await service.enqueue_or_bump(
        ticker="BABA", video_id="v1", channel="c", snippet="s"
    )
    resolved = await service.resolve(row.id, action="dismiss")
    assert resolved.status == "dismissed"
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_add_to_board_requires_board_id(client):
    row = await service.enqueue_or_bump(
        ticker="X", video_id="v", channel="c", snippet="s"
    )
    with pytest.raises(ValueError):
        await service.resolve(row.id, action="add_to_board", board_id=None)


@pytest.mark.asyncio
async def test_resolve_unknown_action_raises(client):
    row = await service.enqueue_or_bump(
        ticker="Y", video_id="v", channel="c", snippet="s"
    )
    with pytest.raises(ValueError):
        await service.resolve(row.id, action="bogus")


@pytest.mark.asyncio
async def test_resolve_missing_entry_raises(client):
    with pytest.raises(LookupError):
        await service.resolve(99999, action="dismiss")


# ---------------------------------------------------------------------------
# Re-eligibility window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismissed_inside_window_does_not_resurface(client):
    row = await service.enqueue_or_bump(
        ticker="WIN", video_id="v1", channel="c", snippet="s"
    )
    await service.resolve(row.id, action="dismiss")
    # Re-mention inside the 90d window.
    again = await service.enqueue_or_bump(
        ticker="WIN", video_id="v2", channel="c2", snippet="s2"
    )
    assert again.status == "dismissed"  # still suppressed
    assert again.times_seen == 2


@pytest.mark.asyncio
async def test_dismissed_past_window_resurfaces_with_chip(client):
    row = await service.enqueue_or_bump(
        ticker="WIN2", video_id="v1", channel="c", snippet="s"
    )
    await service.resolve(row.id, action="dismiss")

    # Force resolved_at into the past (>90d).
    past = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=120)
    async with _db.SessionLocal() as session:
        live = await session.get(TickerReviewEntry, row.id)
        live.resolved_at = past
        await session.commit()

    again = await service.enqueue_or_bump(
        ticker="WIN2", video_id="v2", channel="c2", snippet="s2"
    )
    assert again.status == "pending"
    assert again.previously_dismissed_at is not None


# ---------------------------------------------------------------------------
# Weekly digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weekly_digest_md_renders_pending(client):
    await service.enqueue_or_bump(
        ticker="PLTR", video_id="v1", channel="click", snippet="line one"
    )
    await service.enqueue_or_bump(
        ticker="PLTR", video_id="v2", channel="fx", snippet="line two"
    )
    md = await service.weekly_digest_md()
    assert "Ticker Review Queue" in md
    assert "PLTR" in md
    assert "<!-- ticker-review-queue:auto-start -->" in md
    assert "<!-- ticker-review-queue:auto-end -->" in md


@pytest.mark.asyncio
async def test_weekly_digest_md_handles_empty(client):
    md = await service.weekly_digest_md()
    assert "No pending tickers" in md


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_endpoint_returns_pending(client):
    await service.enqueue_or_bump(
        ticker="PLTR", video_id="v1", channel="c", snippet="s"
    )
    await service.enqueue_or_bump(
        ticker="PLTR", video_id="v2", channel="c", snippet="s"
    )
    resp = await client.get("/v1/ticker-review/queue", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"]
    assert body["items"][0]["ticker"] == "PLTR"


@pytest.mark.asyncio
async def test_resolve_endpoint_dismisses(client):
    row = await service.enqueue_or_bump(
        ticker="BABA", video_id="v", channel="c", snippet="s"
    )
    resp = await client.post(
        f"/v1/ticker-review/{row.id}/resolve",
        headers=HEADERS,
        json={"action": "dismiss"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_resolve_endpoint_unknown_entry_404(client):
    resp = await client.post(
        "/v1/ticker-review/99999/resolve",
        headers=HEADERS,
        json={"action": "dismiss"},
    )
    assert resp.status_code == 404
