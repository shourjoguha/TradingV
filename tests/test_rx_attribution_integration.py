"""Attribution split + explicit linkage end-to-end (retrieval-depth Phase 4).

Confirms rec_influence_kind flows through trade capture (incl. validation +
DB CHECK), explicit linked_hypothesis_ids takes priority over the substring
heuristic in links_for_rec, and the substring path is demoted to fallback.
"""
from __future__ import annotations

import datetime as _dt

import pytest
from sqlalchemy import select, text

from app.core import db as _db
from app.rx import service as rx_service
from app.rx.models import Recommendation
from app.hypotheses.models import Hypothesis
from app.trades.models import Trade


HEADERS = {"X-API-Key": "test-key"}
INGEST_HEADERS = {"X-RX-Ingest-Token": "test-ingest"}


@pytest.fixture(autouse=True)
def _set_ingest_token(monkeypatch):
    from app.core.config import SETTINGS
    monkeypatch.setattr(SETTINGS, "RX_INGEST_TOKEN", "test-ingest")
    yield


async def _seed_rec(client, **overrides) -> str:
    body = {"domain": "finance", "tldr": "seed"}
    body.update(overrides)
    r = await client.post("/v1/rx/recs", json=body, headers=INGEST_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_hyp(slug: str, title: str) -> Hypothesis:
    """Construct a valid Hypothesis row (all non-nullable fields set)."""
    return Hypothesis(
        slug=slug, title=title, claim_type="directional", axis="single_name",
        primary_metric="price", tracking_signal="close", invalidator={},
        ttl_months=6,
        expires_at=_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=180),
        status="active", body_md="x",
    )


# ---- rec_influence_kind through trade capture ------------------------------

@pytest.mark.asyncio
async def test_trade_capture_persists_influence_kind(client):
    rid = await _seed_rec(client)
    r = await client.post(
        "/v1/trades",
        json={
            "ticker": "NVDA", "side": "buy", "qty": 10, "entry_price": 100.0,
            "related_rec_id": rid, "rec_influence_kind": "influenced",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["rec_influence_kind"] == "influenced"


@pytest.mark.asyncio
async def test_influence_kind_requires_related_rec(client):
    r = await client.post(
        "/v1/trades",
        json={"ticker": "NVDA", "side": "buy", "qty": 10, "entry_price": 100.0,
              "rec_influence_kind": "influenced"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "related_rec_id" in r.json()["detail"]


@pytest.mark.asyncio
async def test_influence_kind_rejects_bad_value(client):
    rid = await _seed_rec(client)
    r = await client.post(
        "/v1/trades",
        json={"ticker": "NVDA", "side": "buy", "qty": 10, "entry_price": 100.0,
              "related_rec_id": rid, "rec_influence_kind": "bogus"},
        headers=HEADERS,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_db_check_rejects_bad_influence_kind_direct(client):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        async with _db.SessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO trades "
                    "(id, ticker, side, qty, entry_price, entry_at, fees, "
                    " context_refs, rec_influence_kind) "
                    "VALUES (:i,'X','buy',1,1.0,:t,0,'[]','bogus')"
                ),
                {"i": "33333333-3333-3333-3333-333333333333",
                 "t": _dt.datetime.now(_dt.timezone.utc)},
            )
            await session.commit()


# ---- explicit hypothesis linkage priority (D2 fix) -------------------------

@pytest.mark.asyncio
async def test_explicit_linkage_beats_substring(client):
    # Two hypotheses; the rec text mentions BOTH titles (substring would match
    # both), but only ONE is explicitly linked.
    async with _db.SessionLocal() as session:
        h1 = _mk_hyp("nvda-durable", "nvda")
        h2 = _mk_hyp("meta-cap", "meta")
        session.add_all([h1, h2])
        await session.commit()
        h1_id, h2_id = h1.id, h2.id

    # Rec body mentions both "nvda" and "meta"; only h1 explicitly linked.
    rid = await _seed_rec(
        client,
        tldr="trim nvda, watch meta",
        body_md="nvda durable; meta richly valued",
        linked_hypothesis_ids=[h1_id],
    )
    out = await rx_service.links_for_rec(rid)
    by_id = {h["id"]: h for h in out["hypotheses"]}
    assert by_id[h1_id]["match_type"] == "explicit"
    # h2 still surfaces (substring) but demoted to fallback — never mislabeled
    # as something the operator intended.
    assert by_id[h2_id]["match_type"] == "substring_fallback"


@pytest.mark.asyncio
async def test_explicit_link_not_double_counted(client):
    async with _db.SessionLocal() as session:
        h = _mk_hyp("nvda-durable", "nvda")
        session.add(h)
        await session.commit()
        hid = h.id
    # Rec text contains "nvda" (substring would also match) AND links it.
    rid = await _seed_rec(
        client, tldr="trim nvda", body_md="nvda thesis",
        linked_hypothesis_ids=[hid],
    )
    out = await rx_service.links_for_rec(rid)
    matches = [h for h in out["hypotheses"] if h["id"] == hid]
    assert len(matches) == 1  # surfaced once, as explicit
    assert matches[0]["match_type"] == "explicit"
