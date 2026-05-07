"""Phase 1 tests — ingest, dedupe, fan-out, retention, sync."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

import app.core.db as core_db
from app.alerts.models import Alert
from app.tv_context import service as tvc_service
from app.tv_context.models import (
    KIND_EVENT,
    KIND_IDEA,
    KIND_NOTE,
    KIND_WEBHOOK,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    TVContextItem,
)


HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_webhook_creates_row(client):
    async with core_db.SessionLocal() as session:
        item, deduped = await tvc_service.ingest_webhook(
            session=session,
            ticker="AAPL",
            alert_type="rsi_cross",
            payload_json={"price": 100, "rsi": 30},
        )
        await session.commit()
    assert deduped is False
    assert item.kind == KIND_WEBHOOK
    assert item.ticker == "AAPL"
    assert item.payload["alert_type"] == "rsi_cross"
    assert item.payload["dedupe_count"] == 1
    assert item.expires_at is not None
    assert item.dedupe_key is not None


@pytest.mark.asyncio
async def test_ingest_webhook_dedupes_within_window(client):
    payload = {"price": 100, "rsi": 30}
    async with core_db.SessionLocal() as session:
        first, d1 = await tvc_service.ingest_webhook(
            session=session,
            ticker="AAPL",
            alert_type="rsi_cross",
            payload_json=payload,
        )
        second, d2 = await tvc_service.ingest_webhook(
            session=session,
            ticker="AAPL",
            alert_type="rsi_cross",
            payload_json=payload,
        )
        third, d3 = await tvc_service.ingest_webhook(
            session=session,
            ticker="AAPL",
            alert_type="rsi_cross",
            payload_json=payload,
        )
        await session.commit()

    assert d1 is False
    assert d2 is True
    assert d3 is True
    assert first.id == second.id == third.id
    assert third.payload["dedupe_count"] == 3

    # Different alert_type or ticker should NOT dedupe.
    async with core_db.SessionLocal() as session:
        other, deduped = await tvc_service.ingest_webhook(
            session=session,
            ticker="AAPL",
            alert_type="macd_cross",
            payload_json=payload,
        )
        await session.commit()
    assert deduped is False
    assert other.id != first.id


@pytest.mark.asyncio
async def test_ingest_webhook_outside_window_creates_new(client):
    """Manually advance captured_at on the first row to simulate window
    expiry, then re-ingest. Should NOT dedupe."""
    payload = {"price": 100}
    async with core_db.SessionLocal() as session:
        first, _ = await tvc_service.ingest_webhook(
            session=session,
            ticker="MSFT",
            alert_type="rsi_cross",
            payload_json=payload,
        )
        # Push it 5 min into the past — outside default 60s window.
        first.captured_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=5
        )
        await session.commit()

    async with core_db.SessionLocal() as session:
        second, deduped = await tvc_service.ingest_webhook(
            session=session,
            ticker="MSFT",
            alert_type="rsi_cross",
            payload_json=payload,
        )
        await session.commit()
    assert deduped is False
    assert second.id != first.id


@pytest.mark.asyncio
async def test_ingest_note_idea_event(client):
    async with core_db.SessionLocal() as session:
        note = await tvc_service.ingest_note(
            session=session,
            ticker="NVDA",
            body="seeing a wedge pattern on 4H",
            tags=["pattern", "watch"],
        )
        idea = await tvc_service.ingest_idea(
            session=session,
            ticker="NVDA",
            url="https://www.tradingview.com/chart/abc123/",
            summary="published wedge breakout idea",
        )
        event = await tvc_service.ingest_event(
            session=session,
            ticker="NVDA",
            label="Q3 earnings",
            event_date=datetime.date.today() + datetime.timedelta(days=3),
        )
        await session.commit()
    assert note.kind == KIND_NOTE
    assert idea.kind == KIND_IDEA
    assert event.kind == KIND_EVENT
    assert "tradingview.com" in idea.payload["url"]
    assert event.payload["label"] == "Q3 earnings"
    assert event.expires_at is not None


@pytest.mark.asyncio
async def test_recent_for_ticker_filters(client):
    async with core_db.SessionLocal() as session:
        await tvc_service.ingest_note(session=session, ticker="TSLA", body="a")
        await tvc_service.ingest_note(session=session, ticker="TSLA", body="b")
        await tvc_service.ingest_note(session=session, ticker="GME", body="c")
        await session.commit()

    async with core_db.SessionLocal() as session:
        tsla = await tvc_service.recent_for_ticker(session=session, ticker="TSLA")
        gme = await tvc_service.recent_for_ticker(session=session, ticker="GME")
    assert len(tsla) == 2
    assert len(gme) == 1


@pytest.mark.asyncio
async def test_expire_sweep_flips_status_drops_payload(client):
    async with core_db.SessionLocal() as session:
        item, _ = await tvc_service.ingest_webhook(
            session=session,
            ticker="AAPL",
            alert_type="breakout",
            payload_json={"big_blob": "x" * 5000},
        )
        # Backdate expiry into the past.
        item.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=10
        )
        await session.commit()

    async with core_db.SessionLocal() as session:
        stats = await tvc_service.expire_sweep(session=session, file_unlink=False)
        await session.commit()
    assert stats["expired"] == 1

    async with core_db.SessionLocal() as session:
        result = await session.execute(select(TVContextItem))
        rows = list(result.scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.status == STATUS_EXPIRED
    assert row.heavy_blob_dropped is True
    assert row.tombstone is not None
    assert "summary" in row.tombstone
    # Heavy 'data' field dropped; structural keys retained.
    assert row.payload.get("alert_type") == "breakout"
    assert "data" not in row.payload  # heavy blob nulled


@pytest.mark.asyncio
async def test_expire_sweep_idempotent(client):
    async with core_db.SessionLocal() as session:
        item = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="hello"
        )
        item.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=10
        )
        await session.commit()

    async with core_db.SessionLocal() as session:
        s1 = await tvc_service.expire_sweep(session=session, file_unlink=False)
        await session.commit()
    async with core_db.SessionLocal() as session:
        s2 = await tvc_service.expire_sweep(session=session, file_unlink=False)
        await session.commit()
    assert s1["expired"] == 1
    assert s2["expired"] == 0


# ---------------------------------------------------------------------------
# Webhook fan-out (alerts → tv_context)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_fan_out_creates_alert_and_tv_context(client):
    """Posting to /webhook should write an `alerts` row AND a tv_context_items row
    when payload tags source='tradingview'."""
    payload = {
        "ticker": "AAPL",
        "alert_type": "breakout",
        "payload_json": {"price": 100, "source": "tradingview"},
    }
    r = await client.post("/webhook", json=payload, headers=HEADERS)
    assert r.status_code == 200

    async with core_db.SessionLocal() as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        items = (
            await session.execute(select(TVContextItem))
        ).scalars().all()
    assert len(alerts) == 1
    assert len(items) == 1
    assert items[0].ticker == "AAPL"
    assert items[0].kind == KIND_WEBHOOK


@pytest.mark.asyncio
async def test_webhook_fan_out_dedupes_within_window(client):
    """Five rapid identical webhook posts → 5 alert rows but 1 tv_context row
    with dedupe_count=5."""
    payload = {
        "ticker": "AAPL",
        "alert_type": "rsi_cross",
        "payload_json": {"price": 100, "rsi": 30, "source": "tradingview"},
    }
    for _ in range(5):
        r = await client.post("/webhook", json=payload, headers=HEADERS)
        assert r.status_code == 200

    async with core_db.SessionLocal() as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        items = (
            await session.execute(select(TVContextItem))
        ).scalars().all()
    assert len(alerts) == 5
    assert len(items) == 1
    assert items[0].payload["dedupe_count"] == 5


# ---------------------------------------------------------------------------
# Direct ingest routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_note_route(client):
    r = await client.post(
        "/v1/tv-context/note",
        json={"ticker": "AAPL", "body": "tight wedge", "tags": ["pattern"]},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["item"]["kind"] == "note"
    assert body["item"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_post_idea_route_validates_url(client):
    bad = await client.post(
        "/v1/tv-context/idea",
        json={"url": "https://example.com/foo"},
        headers=HEADERS,
    )
    assert bad.status_code == 400

    good = await client.post(
        "/v1/tv-context/idea",
        json={
            "ticker": "AAPL",
            "url": "https://www.tradingview.com/chart/abc/",
            "summary": "wedge breakout",
        },
        headers=HEADERS,
    )
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_post_event_route_default_expiry(client):
    event_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    r = await client.post(
        "/v1/tv-context/event",
        json={"ticker": "AAPL", "label": "Q3 earnings", "event_date": event_date},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["item"]["payload"]["label"] == "Q3 earnings"
    assert body["item"]["expires_at"] is not None


@pytest.mark.asyncio
async def test_get_by_ticker_filters_active_by_default(client):
    # Ingest one active + one expired note, confirm active-only by default.
    async with core_db.SessionLocal() as session:
        live = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="active"
        )
        old = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="will expire"
        )
        old.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=10
        )
        await session.commit()
    async with core_db.SessionLocal() as session:
        await tvc_service.expire_sweep(session=session, file_unlink=False)
        await session.commit()

    r = await client.get("/v1/tv-context/by-ticker/AAPL", headers=HEADERS)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "active"

    r2 = await client.get(
        "/v1/tv-context/by-ticker/AAPL?include_expired=true", headers=HEADERS
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 2


@pytest.mark.asyncio
async def test_archive_route_drops_payload(client):
    async with core_db.SessionLocal() as session:
        item = await tvc_service.ingest_note(
            session=session,
            ticker="AAPL",
            body="lots of detail" * 50,
        )
        await session.commit()
        item_id = item.id

    r = await client.post(
        f"/v1/tv-context/{item_id}/archive", headers=HEADERS
    )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "archived"
    assert out["heavy_blob_dropped"] is True
    assert out["tombstone"] is not None


@pytest.mark.asyncio
async def test_import_endpoint_idempotent(client):
    """Peer-side ingest re-uses upstream id; double-post is no-op."""
    payload = {
        "id": "imported-1",
        "kind": "note",
        "ticker": "AAPL",
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "expires_at": (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30)
        ).isoformat(),
        "payload": {"body": "imported"},
    }
    for _ in range(3):
        r = await client.post(
            "/v1/tv-context/import", json=payload, headers=HEADERS
        )
        assert r.status_code == 200

    async with core_db.SessionLocal() as session:
        rows = (
            await session.execute(select(TVContextItem))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == "imported-1"


@pytest.mark.asyncio
async def test_auth_required(client):
    r = await client.post(
        "/v1/tv-context/note", json={"body": "hi"}
    )
    assert r.status_code in (401, 403)
    r2 = await client.get("/v1/tv-context/by-ticker/AAPL")
    assert r2.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Sync outbox enqueue (kind=tv_context_*)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Vault writer (Phase 2 file-write helpers)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vault_writer_writes_image_and_sidecar(client, tmp_path, monkeypatch):
    """`write_screenshot` writes both the image and a sidecar markdown
    with frontmatter + embedded image link."""
    from app.tv_context import vault as _vault

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))

    result = _vault.write_screenshot(
        ticker="aapl",
        image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        operator_note="wedge breakout 4H",
        hypothesis_id="hyp-1",
    )

    assert result.image_path.exists()
    assert result.sidecar_path.exists()
    body = result.sidecar_path.read_text(encoding="utf-8")
    assert "ticker: AAPL" in body
    assert "kind: tradingview-screenshot" in body
    assert "hypothesis_id: hyp-1" in body
    assert f"![[{result.image_filename}]]" in body
    assert "wedge breakout 4H" in body


@pytest.mark.asyncio
async def test_vault_writer_no_collision_on_same_second(client, tmp_path, monkeypatch):
    """Two writes within the same HHMMSS use different shortids → no overwrite."""
    from app.tv_context import vault as _vault

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    a = _vault.write_screenshot(ticker="X", image_bytes=b"1")
    b = _vault.write_screenshot(ticker="X", image_bytes=b"2")
    assert a.image_path != b.image_path
    assert a.image_path.read_bytes() == b"1"
    assert b.image_path.read_bytes() == b"2"


@pytest.mark.asyncio
async def test_vault_append_vision_block_idempotent(client, tmp_path, monkeypatch):
    from app.tv_context import vault as _vault

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    result = _vault.write_screenshot(ticker="AAPL", image_bytes=b"x")
    _vault.append_vision_block(
        sidecar_path=result.sidecar_path, vision_md="**Structured**\n- ticker: AAPL"
    )
    body1 = result.sidecar_path.read_text(encoding="utf-8")
    assert body1.count("vision-summary:start") == 1

    _vault.append_vision_block(
        sidecar_path=result.sidecar_path,
        vision_md="**Structured**\n- ticker: AAPL (refreshed)",
    )
    body2 = result.sidecar_path.read_text(encoding="utf-8")
    assert body2.count("vision-summary:start") == 1
    assert "refreshed" in body2


@pytest.mark.asyncio
async def test_screenshot_route_503_when_vault_unset(client, monkeypatch):
    """With VAULT_PATH explicitly empty, screenshot ingest returns 503."""
    monkeypatch.setenv("VAULT_PATH", "")
    files = {"file": ("chart.png", b"fakebytes", "image/png")}
    data = {"ticker": "AAPL", "vision_enabled": "false"}
    r = await client.post(
        "/v1/tv-context/screenshot",
        files=files,
        data=data,
        headers=HEADERS,
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_screenshot_route_with_vault(client, tmp_path, monkeypatch):
    """End-to-end screenshot ingest with vision disabled — file lands, row created."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    files = {"file": ("chart.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")}
    data = {"ticker": "AAPL", "note": "tight wedge", "vision_enabled": "false"}
    r = await client.post(
        "/v1/tv-context/screenshot",
        files=files,
        data=data,
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item"]["kind"] == "screenshot"
    assert body["item"]["ticker"] == "AAPL"
    assert body["item"]["vault_path"] is not None
    # File on disk.
    from pathlib import Path
    assert Path(body["item"]["vault_path"]).exists()


# ---------------------------------------------------------------------------
# Trade-close enrichment (Phase 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_on_trade_close_links_items(client):
    """Closing a trade walks recent tv_context items in window and stamps
    tombstones with trade_id + outcome."""
    from app.trades.models import Trade

    entry_at = datetime.datetime.now(datetime.timezone.utc)
    async with core_db.SessionLocal() as session:
        in_window = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="setup looks tight"
        )
        # Push another note OUTSIDE the window (48h+).
        out_window = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="old observation"
        )
        out_window.captured_at = entry_at - datetime.timedelta(days=5)
        trade = Trade(
            id="trade-1",
            ticker="AAPL",
            side="buy",
            qty=10,
            entry_price=100.0,
            entry_at=entry_at,
            exit_price=110.0,
            exit_at=entry_at + datetime.timedelta(hours=4),
            realized_pnl=100.0,
        )
        session.add(trade)
        await session.commit()

        stats = await tvc_service.enrich_on_trade_close(
            session=session,
            trade_id=trade.id,
            ticker=trade.ticker,
            entry_at=trade.entry_at,
            exit_at=trade.exit_at,
            realized_pnl=trade.realized_pnl,
        )
        await session.commit()

    assert stats["linked"] == 1

    async with core_db.SessionLocal() as session:
        items = await tvc_service.list_for_trade(session=session, trade_id="trade-1")
    assert len(items) == 1
    assert items[0].id == in_window.id
    assert items[0].tombstone is not None
    assert any(t["trade_id"] == "trade-1" for t in items[0].tombstone["trades"])


# ---------------------------------------------------------------------------
# Vision spend aggregation (Phase 6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_spend_aggregates_costs(client):
    """Vision-spend endpoint sums payload.vision.cost_usd within a month."""
    async with core_db.SessionLocal() as session:
        item1 = await tvc_service.ingest_screenshot_row(
            session=session,
            ticker="AAPL",
            vault_path="/tmp/x1.md",
            payload={"vision": {"cost_usd": 0.012}},
        )
        item2 = await tvc_service.ingest_screenshot_row(
            session=session,
            ticker="AAPL",
            vault_path="/tmp/x2.md",
            payload={"vision": {"cost_usd": 0.008}},
        )
        await session.commit()
        captured = item1.captured_at

    r = await client.get(
        f"/v1/tv-context/vision-spend?month={captured.strftime('%Y-%m')}",
        headers=HEADERS,
    )
    assert r.status_code == 200
    out = r.json()
    assert out["call_count"] == 2
    assert abs(out["total_usd"] - 0.02) < 1e-6


# ---------------------------------------------------------------------------
# Sync outbox enqueue (kind=tv_context_*)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Trade-close → tv_context enrichment HTTP wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_trade_close_enriches_tv_context(client):
    """PATCH /v1/trades/{id} that flips exit_price from null → value should
    walk recent tv_context items in entry_at±24h and stamp tombstones."""
    entry_at = datetime.datetime.now(datetime.timezone.utc)

    # Note ingested in-window AND a note out-of-window.
    async with core_db.SessionLocal() as session:
        in_window = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="setup looks tight"
        )
        out_window = await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="old observation"
        )
        out_window.captured_at = entry_at - datetime.timedelta(days=5)
        await session.commit()
        in_id = in_window.id

    # Create open trade.
    create_resp = await client.post(
        "/v1/trades",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "qty": 10,
            "entry_price": 100.0,
            "entry_at": entry_at.isoformat(),
        },
        headers=HEADERS,
    )
    assert create_resp.status_code == 200
    trade_id = create_resp.json()["id"]

    # Close it via PATCH — should trigger enrichment.
    patch_resp = await client.patch(
        f"/v1/trades/{trade_id}",
        json={
            "exit_price": 110.0,
            "exit_at": (entry_at + datetime.timedelta(hours=4)).isoformat(),
        },
        headers=HEADERS,
    )
    assert patch_resp.status_code == 200
    closed = patch_resp.json()
    assert closed["realized_pnl"] is not None

    # In-window item should be linked + tombstone stamped.
    async with core_db.SessionLocal() as session:
        from app.trades.models import Trade
        from app.tv_context.models import TVContextItem

        trade = await session.get(Trade, trade_id)
        assert trade.context_refs == [in_id]

        item = await session.get(TVContextItem, in_id)
        assert item.tombstone is not None
        trades_list = item.tombstone.get("trades") or []
        assert any(t["trade_id"] == trade_id for t in trades_list)


@pytest.mark.asyncio
async def test_patch_trade_close_idempotent(client):
    """Re-PATCHing a closed trade (e.g. updating fees) does NOT double-link
    or duplicate tombstone outcomes."""
    entry_at = datetime.datetime.now(datetime.timezone.utc)
    async with core_db.SessionLocal() as session:
        item = await tvc_service.ingest_note(
            session=session, ticker="MSFT", body="window note"
        )
        await session.commit()
        item_id = item.id

    create_resp = await client.post(
        "/v1/trades",
        json={
            "ticker": "MSFT",
            "side": "buy",
            "qty": 5,
            "entry_price": 200.0,
            "entry_at": entry_at.isoformat(),
        },
        headers=HEADERS,
    )
    trade_id = create_resp.json()["id"]

    # First PATCH closes the trade — enrichment fires.
    await client.patch(
        f"/v1/trades/{trade_id}",
        json={
            "exit_price": 210.0,
            "exit_at": (entry_at + datetime.timedelta(hours=2)).isoformat(),
        },
        headers=HEADERS,
    )

    # Second PATCH only updates fees — should NOT re-enrich.
    await client.patch(
        f"/v1/trades/{trade_id}",
        json={"fees": 1.50},
        headers=HEADERS,
    )

    async with core_db.SessionLocal() as session:
        from app.tv_context.models import TVContextItem

        item = await session.get(TVContextItem, item_id)
        trades_list = item.tombstone.get("trades") or []
        # Exactly one entry, not two.
        assert len(trades_list) == 1


# ---------------------------------------------------------------------------
# Phase 4 — research/ask gating layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_ask_gates_when_context_missing(client, monkeypatch):
    """A flagged hypothesis with no TV-context items + tickers supplied
    should short-circuit with status='needs_context' (no LLM call)."""
    from app.hypotheses.models import Hypothesis

    # Create a hypothesis with requires_tv_context=True.
    async with core_db.SessionLocal() as session:
        h = Hypothesis(
            slug="aapl-wedge-2026q2",
            title="AAPL wedge breakout",
            claim_type="single_name",
            axis="equity:AAPL",
            primary_metric="close",
            tracking_signal="rsi",
            invalidator={"op": "manual", "args": {}},
            ttl_months=3,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30),
            requires_tv_context=True,
        )
        session.add(h)
        await session.commit()

    # ANTHROPIC_API_KEY missing — would normally fail in client.ask_claude.
    # The gate must short-circuit BEFORE the call.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    r = await client.post(
        "/v1/research/ask",
        json={
            "query": "is the wedge still valid?",
            "hypothesis_slugs": ["aapl-wedge-2026q2"],
            "tickers": ["AAPL"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_context"
    assert body["context_check"]
    assert body["context_check"][0]["ticker"] == "AAPL"
    assert body["context_check"][0]["needs_context"] is True
    # No LLM tokens charged.
    assert body["tokens_in"] == 0
    assert body["tokens_out"] == 0


@pytest.mark.asyncio
async def test_research_ask_proceeds_when_context_present(client, monkeypatch):
    """When recent tv_context items exist for the supplied tickers, the
    gate lets the request through (and would call Claude — we mock that)."""
    from app.hypotheses.models import Hypothesis

    async with core_db.SessionLocal() as session:
        h = Hypothesis(
            slug="aapl-wedge-with-ctx",
            title="AAPL with context",
            claim_type="single_name",
            axis="equity:AAPL",
            primary_metric="close",
            tracking_signal="rsi",
            invalidator={"op": "manual", "args": {}},
            ttl_months=3,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30),
            requires_tv_context=True,
        )
        session.add(h)
        await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="setup looks tight"
        )
        await session.commit()

    # Mock the Claude call so we don't need a real API key.
    from app.research import client as _research_client

    class _FakeResult:
        verdict_text = "stub verdict"
        tool_calls: list = []
        tokens_in = 0
        tokens_out = 0
        cache_read_tokens = 0
        est_cost_usd = 0.0
        raw: dict = {}

    async def _fake_ask(*_args, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(_research_client, "ask_claude", _fake_ask)

    r = await client.post(
        "/v1/research/ask",
        json={
            "query": "is the wedge still valid?",
            "hypothesis_slugs": ["aapl-wedge-with-ctx"],
            "tickers": ["AAPL"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] != "needs_context"
    assert body["context_check"][0]["available_count"] >= 1


@pytest.mark.asyncio
async def test_research_ask_force_skip_overrides_gate(client, monkeypatch):
    """force_skip_context_gate=True should bypass the gate even when
    tickers are missing context."""
    from app.hypotheses.models import Hypothesis

    async with core_db.SessionLocal() as session:
        h = Hypothesis(
            slug="aapl-wedge-skip",
            title="AAPL wedge skip",
            claim_type="single_name",
            axis="equity:AAPL",
            primary_metric="close",
            tracking_signal="rsi",
            invalidator={"op": "manual", "args": {}},
            ttl_months=3,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30),
            requires_tv_context=True,
        )
        session.add(h)
        await session.commit()

    from app.research import client as _research_client

    class _FakeResult:
        verdict_text = "stub"
        tool_calls: list = []
        tokens_in = 0
        tokens_out = 0
        cache_read_tokens = 0
        est_cost_usd = 0.0
        raw: dict = {}

    async def _fake_ask(*_args, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(_research_client, "ask_claude", _fake_ask)

    r = await client.post(
        "/v1/research/ask",
        json={
            "query": "force",
            "hypothesis_slugs": ["aapl-wedge-skip"],
            "tickers": ["AAPL"],
            "force_skip_context_gate": True,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] != "needs_context"


@pytest.mark.asyncio
async def test_outbox_kinds_enqueued_when_peer_configured(client, monkeypatch):
    """When PEER_API_URL is set, ingesting a note enqueues a kind=tv_context_note row."""
    from app.core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "PEER_API_URL", "https://peer.example.com")
    monkeypatch.setattr(SETTINGS, "PEER_API_KEY", "peer-key")

    async with core_db.SessionLocal() as session:
        await tvc_service.ingest_note(
            session=session, ticker="AAPL", body="sync me"
        )
        await session.commit()

    from app.sync.models import SyncOutbox

    async with core_db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(SyncOutbox).where(SyncOutbox.kind == "tv_context_note")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload_json["ticker"] == "AAPL"
