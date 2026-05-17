"""rx (prescription) layer — finance recommendations endpoints.

Covers:
  * ingest auth: missing/bad token rejected; 503 when env unset
  * CHECK constraint rejects non-finance domain at DB level
  * list endpoint filters to finance + applies status ordering
  * detail / disposition / snooze writes
  * subjective_fit required on acted_* dispositions
  * snooze count increments; forced-decision flag at >=2
  * auto-revive flag on past-due snooze rows
  * trades.related_rec_id FK persists across rec deletion (SET NULL)
"""
from __future__ import annotations

import datetime as _dt
import os

import pytest
from sqlalchemy import select, text

from app.core import db as _db
from app.rx import service
from app.rx.models import Recommendation
from app.trades.models import Trade


HEADERS = {"X-API-Key": "test-key"}
INGEST_HEADERS = {"X-RX-Ingest-Token": "test-ingest"}


@pytest.fixture(autouse=True)
def _set_ingest_token(monkeypatch):
    # Wire ingest token for tests; reset between tests via monkeypatch.
    from app.core.config import SETTINGS
    monkeypatch.setattr(SETTINGS, "RX_INGEST_TOKEN", "test-ingest")
    yield


# ---------------------------------------------------------------------------
# Ingest auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_rejects_missing_token(client):
    r = await client.post(
        "/v1/rx/recs",
        json={"domain": "finance", "tldr": "test"},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_ingest_rejects_bad_token(client):
    r = await client.post(
        "/v1/rx/recs",
        json={"domain": "finance"},
        headers={"X-RX-Ingest-Token": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_ingest_503_when_token_unset(client, monkeypatch):
    from app.core.config import SETTINGS
    monkeypatch.setattr(SETTINGS, "RX_INGEST_TOKEN", "")
    r = await client.post(
        "/v1/rx/recs",
        json={"domain": "finance"},
        headers={"X-RX-Ingest-Token": "anything"},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_ingest_creates_finance_rec(client):
    from app.core.config import SETTINGS
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "drift_score": 0.42,
            "confidence": 71,
            "tldr": "Trim AAPL on guide cut",
            "body_md": "# Recommendation\n\nTrim 25%.",
            "rx_md_path": "Lakshmi/rx/rx-fin-2026-05-16-00.md",
            "signals_fired": ["thesis_decay", "earnings_blackout"],
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["domain"] == "finance"
    assert body["status"] == "open"
    assert body["drift_score"] == 0.42
    assert body["confidence"] == 71
    assert body["snooze_count"] == 0
    # Server-stamped: must match env, NEVER the client value.
    assert body["owner_user_id"] == SETTINGS.RX_OPERATOR_UUID
    assert len(body["id"]) == 36
    assert body["forced_decision"] is False


@pytest.mark.asyncio
async def test_ingest_ignores_client_owner_user_id(client):
    """Hard rule: client-supplied owner_user_id MUST be ignored."""
    from app.core.config import SETTINGS
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "x",
            # Pydantic schema does not declare this field — extras ignored.
            "owner_user_id": "00000000-attacker-supplied-0000-000000000000",
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["owner_user_id"] == SETTINGS.RX_OPERATOR_UUID


# ---------------------------------------------------------------------------
# Domain enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_rejects_non_finance_domain(client):
    r = await client.post(
        "/v1/rx/recs",
        json={"domain": "fitness", "tldr": "x"},
        headers=INGEST_HEADERS,
    )
    # Pydantic Literal rejects at 422.
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_db_check_rejects_non_finance_direct_insert(client):
    """Defense-in-depth: even if validation is bypassed, DB CHECK blocks."""
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        async with _db.SessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO recommendations "
                    "(id, owner_user_id, domain, status, snooze_count) "
                    "VALUES (:i, :o, 'fitness', 'open', 0)"
                ),
                {"i": "11111111-1111-1111-1111-111111111111", "o": "u"},
            )
            await session.commit()


# ---------------------------------------------------------------------------
# List + detail
# ---------------------------------------------------------------------------

async def _seed_rec(client, **overrides) -> str:
    body = {"domain": "finance", "tldr": "seed"}
    body.update(overrides)
    r = await client.post("/v1/rx/recs", json=body, headers=INGEST_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_list_returns_seeded(client):
    rid = await _seed_rec(client, tldr="hello world")
    r = await client.get("/v1/rx/recs", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == rid
    assert item["short_id"] == rid[:8]
    assert item["tldr_short"] == "hello world"
    assert item["status"] == "open"
    assert item["age_days"] == 0
    assert item["forced_decision"] is False
    assert item["aging"] is False


@pytest.mark.asyncio
async def test_list_status_ordering(client):
    # open after acted+dismissed insertion order — open must come first.
    open_id = await _seed_rec(client, tldr="open-rec")
    acted_id = await _seed_rec(client, tldr="acted-rec")
    dismissed_id = await _seed_rec(client, tldr="dismissed-rec")
    await client.post(
        f"/v1/rx/recs/{acted_id}/disposition",
        json={"disposition": "acted_as_prescribed", "subjective_fit_1_5": 4},
        headers=HEADERS,
    )
    await client.post(
        f"/v1/rx/recs/{dismissed_id}/disposition",
        json={"disposition": "dismissed"},
        headers=HEADERS,
    )
    r = await client.get("/v1/rx/recs", headers=HEADERS)
    items = r.json()["items"]
    statuses = [it["status"] for it in items]
    assert statuses[0] == "open"
    # acted before dismissed
    assert statuses.index("acted") < statuses.index("dismissed")


@pytest.mark.asyncio
async def test_get_detail(client):
    rid = await _seed_rec(client, body_md="# Hello\n\nbody")
    r = await client.get(f"/v1/rx/recs/{rid}", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["body_md"] == "# Hello\n\nbody"
    assert body["domain"] == "finance"


@pytest.mark.asyncio
async def test_get_404_unknown(client):
    r = await client.get("/v1/rx/recs/00000000-0000-0000-0000-000000000000", headers=HEADERS)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Disposition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disposition_acted_requires_fit(client):
    rid = await _seed_rec(client)
    r = await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={"disposition": "acted_as_prescribed"},
        headers=HEADERS,
    )
    assert r.status_code == 422  # pydantic model_validator


@pytest.mark.asyncio
async def test_disposition_skipped_no_fit_needed(client):
    rid = await _seed_rec(client)
    r = await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={"disposition": "skipped", "outcome_note": "no time"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "acted"
    assert body["acted_disposition"] == "skipped"
    assert body["outcome_note"] == "no time"
    assert body["acted_at"] is not None


@pytest.mark.asyncio
async def test_disposition_acted_modified_persists_fit(client):
    rid = await _seed_rec(client)
    r = await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={
            "disposition": "acted_modified",
            "subjective_fit_1_5": 3,
            "outcome_note": "trimmed half not all",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "acted"
    assert body["subjective_fit_1_5"] == 3


@pytest.mark.asyncio
async def test_disposition_dismissed_skips_acted_at(client):
    rid = await _seed_rec(client)
    r = await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={"disposition": "dismissed"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "dismissed"
    assert body["acted_disposition"] == "dismissed"


# ---------------------------------------------------------------------------
# Snooze
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snooze_increments_count(client):
    rid = await _seed_rec(client)
    r = await client.post(
        f"/v1/rx/recs/{rid}/snooze", json={"days": 2}, headers=HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "snoozed"
    assert body["snooze_count"] == 1
    assert body["snoozed_until"]

    r2 = await client.post(
        f"/v1/rx/recs/{rid}/snooze", json={"days": 1}, headers=HEADERS
    )
    body2 = r2.json()
    assert body2["snooze_count"] == 2


@pytest.mark.asyncio
async def test_snooze_rejects_out_of_range_days(client):
    rid = await _seed_rec(client)
    r = await client.post(
        f"/v1/rx/recs/{rid}/snooze", json={"days": 30}, headers=HEADERS
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_marks_forced_and_auto_revived(client):
    rid = await _seed_rec(client)
    # Force snooze_count >= 2 and snoozed_until in the past.
    async with _db.SessionLocal() as session:
        row = await session.scalar(
            select(Recommendation).where(Recommendation.id == rid)
        )
        row.snooze_count = 3
        row.status = "snoozed"
        row.snoozed_until = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1)
        await session.commit()
    r = await client.get("/v1/rx/recs", headers=HEADERS)
    item = r.json()["items"][0]
    assert item["forced_decision"] is True
    assert item["auto_revived"] is True


# ---------------------------------------------------------------------------
# trades.related_rec_id FK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trades_related_rec_id_set_null_on_delete(client):
    rid = await _seed_rec(client)
    # Insert a trade linked to the rec.
    async with _db.SessionLocal() as session:
        t = Trade(
            ticker="AAPL",
            side="buy",
            qty=10,
            entry_price=190.0,
            entry_at=_dt.datetime.now(_dt.timezone.utc),
            related_rec_id=rid,
        )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        tid = t.id
    # Delete rec; trade should survive with related_rec_id=NULL.
    async with _db.SessionLocal() as session:
        rec = await session.scalar(
            select(Recommendation).where(Recommendation.id == rid)
        )
        await session.delete(rec)
        await session.commit()
    async with _db.SessionLocal() as session:
        t2 = await session.scalar(select(Trade).where(Trade.id == tid))
        assert t2 is not None
        assert t2.related_rec_id is None


# ---------------------------------------------------------------------------
# Window + limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_window_filters_old_rows(client):
    rid = await _seed_rec(client)
    # Backdate beyond default 60d window.
    async with _db.SessionLocal() as session:
        row = await session.scalar(
            select(Recommendation).where(Recommendation.id == rid)
        )
        row.created_at = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=90)
        await session.commit()
    r = await client.get("/v1/rx/recs?window_days=30", headers=HEADERS)
    assert r.json()["count"] == 0
    r2 = await client.get("/v1/rx/recs?window_days=120", headers=HEADERS)
    assert r2.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_validates_params(client):
    r = await client.get("/v1/rx/recs?window_days=0", headers=HEADERS)
    assert r.status_code == 400
    r2 = await client.get("/v1/rx/recs?limit=999", headers=HEADERS)
    assert r2.status_code == 400


# ---------------------------------------------------------------------------
# Created_at honors payload override
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_created_at_payload_honored(client):
    ts = "2026-05-15T10:00:00+00:00"
    r = await client.post(
        "/v1/rx/recs",
        json={"domain": "finance", "tldr": "old", "created_at": ts},
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["created_at"].startswith("2026-05-15")


@pytest.mark.asyncio
async def test_created_at_naive_is_coerced_to_utc(client):
    """Naive datetimes (no tz suffix) must be coerced to UTC server-side."""
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "naive ts",
            "created_at": "2026-05-15T10:00:00",
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    # Confirm subsequent reads work — proves the comparison in list_recs
    # didn't blow up on aware-vs-naive.
    r2 = await client.get("/v1/rx/recs", headers=HEADERS)
    assert r2.status_code == 200
    assert any(it["id"] == rid for it in r2.json()["items"])


# ---------------------------------------------------------------------------
# Terminal-state mutation guards (HIGH issue #1 from audit)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disposition_rejected_on_terminal_rec(client):
    rid = await _seed_rec(client)
    # First disposition: dismiss.
    r = await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={"disposition": "dismissed"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    # Second disposition: rejected.
    r2 = await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={"disposition": "acted_as_prescribed", "subjective_fit_1_5": 4},
        headers=HEADERS,
    )
    assert r2.status_code == 400
    assert "terminal" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_snooze_rejected_on_terminal_rec(client):
    rid = await _seed_rec(client)
    await client.post(
        f"/v1/rx/recs/{rid}/disposition",
        json={"disposition": "skipped"},
        headers=HEADERS,
    )
    r2 = await client.post(
        f"/v1/rx/recs/{rid}/snooze",
        json={"days": 1},
        headers=HEADERS,
    )
    assert r2.status_code == 400
    assert "terminal" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_detail_includes_forced_decision_field(client):
    rid = await _seed_rec(client)
    # Snooze twice to flip the flag.
    await client.post(f"/v1/rx/recs/{rid}/snooze", json={"days": 1}, headers=HEADERS)
    await client.post(f"/v1/rx/recs/{rid}/snooze", json={"days": 1}, headers=HEADERS)
    r = await client.get(f"/v1/rx/recs/{rid}", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["forced_decision"] is True
    assert body["snooze_count"] == 2
