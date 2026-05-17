"""rx attention signal — Phase 2 (tv-context-decision-engine-enrichment).

Covers:
  * compute_attention pure math (decay, kind weights, empty universe)
  * compute_attention_for_rec extracts tickers (denylist applied)
  * compute_attention_for_rec aggregates score = MAX across tickers
  * service.create stamps attention_score + attention_breakdown
  * list_recs surfaces attention fields
  * GET /v1/rx/recs/{id} returns attention fields
"""
from __future__ import annotations

import datetime as _dt

import pytest

from app.core import db as _db
from app.core.config import SETTINGS
from app.rx import service as rx_svc
from app.rx import tv_context_signal as sig
from app.tv_context import service as tvc_svc


HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def _set_ingest_token(monkeypatch):
    monkeypatch.setattr(SETTINGS, "RX_INGEST_TOKEN", "test-ingest")
    monkeypatch.setattr(SETTINGS, "RX_OPERATOR_UUID", "11111111-1111-1111-1111-111111111111")
    yield


# ---------------------------------------------------------------------------
# Pure math — decay + weights
# ---------------------------------------------------------------------------


def test_decay_floors_at_zero_and_halves_at_halflife():
    """exp(-ln2 * age / half_life). Boundary checks."""
    # age=0 → 1.0
    assert sig._decay(0) == pytest.approx(1.0)
    # age=half_life → 0.5
    assert sig._decay(sig.HALF_LIFE_DAYS) == pytest.approx(0.5, rel=1e-6)
    # negative age → coerced to 0 → 1.0
    assert sig._decay(-5.0) == pytest.approx(1.0)
    # 10× half_life → effectively 0
    assert sig._decay(sig.HALF_LIFE_DAYS * 10) < 1e-3


def test_extract_tickers_applies_denylist():
    """Common noise tokens (BUY, USA, GDP) never become tickers."""
    text = "Buy NVDA today; USA GDP looks weak. Watch META and AAPL."
    out = sig.extract_tickers(tldr="position update", body_md=text)
    assert "NVDA" in out
    assert "META" in out
    assert "AAPL" in out
    assert "BUY" not in out
    assert "USA" not in out
    assert "GDP" not in out


# ---------------------------------------------------------------------------
# compute_attention — empty universe + populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_attention_empty_universe_returns_zero(client):
    """No TV-context rows → score 0.0, breakdown all zeros."""
    out = await sig.compute_attention("PLTR")
    assert out["score"] == 0.0
    assert all(v == 0 for v in out["breakdown"].values())


@pytest.mark.asyncio
async def test_compute_attention_weights_screenshots_highest(client):
    """One screenshot + one webhook on same ticker, both at t=0:
    score = 1.0 * 1.0 + 0.2 * 1.0 = 1.2."""
    async with _db.SessionLocal() as session:
        await tvc_svc.ingest_screenshot_row(
            session=session,
            ticker="NVDA",
            vault_path="/tmp/x.md",
            payload={"note": "chart"},
        )
        await tvc_svc.ingest_webhook(
            session=session,
            ticker="NVDA",
            alert_type="rsi",
            payload_json={"v": 1},
        )
        await session.commit()

    out = await sig.compute_attention("NVDA")
    # Allow a hair of decay (a few ms of age). Both should be near full weight.
    assert out["score"] == pytest.approx(1.2, abs=0.05)
    assert out["breakdown"][tvc_svc.KIND_SCREENSHOT] == 1
    assert out["breakdown"][tvc_svc.KIND_WEBHOOK] == 1


@pytest.mark.asyncio
async def test_compute_attention_decays_older_items(client):
    """Same screenshot but 14d old → ~0.25 weighted; 0d old → ~1.0.
    At 14d old, decay = 2^-2 = 0.25."""
    now = _dt.datetime.now(_dt.timezone.utc)
    old = now - _dt.timedelta(days=14)
    async with _db.SessionLocal() as session:
        # Manually inject a row at known captured_at.
        from app.tv_context.models import TVContextItem, KIND_SCREENSHOT, STATUS_ACTIVE

        session.add(
            TVContextItem(
                kind=KIND_SCREENSHOT,
                ticker="META",
                source="tradingview",
                captured_at=old,
                expires_at=now + _dt.timedelta(days=30),
                status=STATUS_ACTIVE,
                payload={"note": "old chart"},
                vault_path="/tmp/old.md",
                created_at=old,
                updated_at=old,
            )
        )
        await session.commit()

    out = await sig.compute_attention("META", now=now)
    # 1.0 weight × 2^-2 = 0.25
    assert out["score"] == pytest.approx(0.25, abs=0.02)


@pytest.mark.asyncio
async def test_compute_attention_for_rec_aggregates_max(client):
    """A rec mentioning NVDA + META with different attention picks MAX."""
    async with _db.SessionLocal() as session:
        # NVDA: 1 screenshot (heaviest) → score ≈ 1.0
        await tvc_svc.ingest_screenshot_row(
            session=session,
            ticker="NVDA",
            vault_path="/tmp/nvda.md",
            payload={"note": "x"},
        )
        # META: 1 idea (lighter) → score ≈ 0.5
        await tvc_svc.ingest_idea(
            session=session,
            ticker="META",
            url="https://example.com",
            summary="thoughts",
        )
        await session.commit()

    out = await sig.compute_attention_for_rec(
        tldr="Long NVDA puts; META catalyst pending",
        body_md=None,
    )
    # MAX(NVDA ≈ 1.0, META ≈ 0.5) ≈ 1.0
    assert out["score"] == pytest.approx(1.0, abs=0.05)
    assert "NVDA" in out["breakdown"]
    assert "META" in out["breakdown"]
    assert out["breakdown"]["NVDA"]["score"] > out["breakdown"]["META"]["score"]


# ---------------------------------------------------------------------------
# Integration with rx.service.create + list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rec_stamps_attention_when_tv_context_exists(client):
    """rec creation pulls recent TV-context items into attention_score."""
    async with _db.SessionLocal() as session:
        await tvc_svc.ingest_screenshot_row(
            session=session,
            ticker="AAPL",
            vault_path="/tmp/aapl.md",
            payload={"note": "chart"},
        )
        await session.commit()

    rec = await rx_svc.create(
        domain="finance",
        tldr="AAPL setup looks clean",
        body_md="entry at 175",
    )
    assert rec.attention_score is not None
    assert rec.attention_score > 0
    assert isinstance(rec.attention_breakdown, dict)
    assert "AAPL" in rec.attention_breakdown


@pytest.mark.asyncio
async def test_create_rec_zero_attention_when_no_tv_context(client):
    """No TV-context for any mentioned ticker → score 0.0 + empty breakdown."""
    rec = await rx_svc.create(
        domain="finance",
        tldr="TSLA earnings preview",
        body_md=None,
    )
    assert rec.attention_score == 0.0


@pytest.mark.asyncio
async def test_list_recs_surfaces_attention_fields(client):
    """list_recs returns attention_score + attention_breakdown."""
    async with _db.SessionLocal() as session:
        await tvc_svc.ingest_note(
            session=session, ticker="META", body="upgrade thoughts"
        )
        await session.commit()

    await rx_svc.create(
        domain="finance",
        tldr="META long",
        body_md="entry 470",
    )
    items = await rx_svc.list_recs()
    assert len(items) == 1
    assert items[0]["attention_score"] is not None
    assert items[0]["attention_breakdown"] is not None


@pytest.mark.asyncio
async def test_get_rec_endpoint_returns_attention(client):
    """GET /v1/rx/recs/{id} surfaces attention_score + breakdown."""
    async with _db.SessionLocal() as session:
        await tvc_svc.ingest_screenshot_row(
            session=session,
            ticker="NVDA",
            vault_path="/tmp/n.md",
            payload={"note": "x"},
        )
        await session.commit()

    rec = await rx_svc.create(
        domain="finance",
        tldr="NVDA call spread",
        body_md=None,
    )
    r = await client.get(f"/v1/rx/recs/{rec.id}", headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "attention_score" in body
    assert "attention_breakdown" in body
    assert body["attention_score"] > 0


@pytest.mark.asyncio
async def test_create_rec_attention_failure_does_not_block(client, monkeypatch):
    """A compute failure must not stop rec creation."""
    async def _boom(**kwargs):
        raise RuntimeError("simulated")

    monkeypatch.setattr(
        "app.rx.tv_context_signal.compute_attention_for_rec", _boom
    )

    rec = await rx_svc.create(
        domain="finance",
        tldr="Should still create",
        body_md=None,
    )
    assert rec.id is not None
    # Default value when compute didn't run: attention_score is None
    # (because the assignment inside `create` never ran). Caller-side
    # serialization handles None → 0.0 in UI.
    assert rec.attention_score is None
