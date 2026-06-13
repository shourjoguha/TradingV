"""rx deep-result store — POST/GET /v1/rx/deep (retrieval-depth Phase 0).

Covers:
  * ingest auth: missing/bad token rejected (write = ingest token)
  * read auth: API key required
  * kind CHECK + Literal validation
  * rec_id / query_hash requirement (≥1)
  * owner stamped server-side
  * list filters by rec_id / query_hash / kind; rejects unscoped scan
  * DB CHECK rejects bad kind on direct insert (defense-in-depth)
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core import db as _db


HEADERS = {"X-API-Key": "test-key"}
INGEST_HEADERS = {"X-RX-Ingest-Token": "test-ingest"}


@pytest.fixture(autouse=True)
def _set_ingest_token(monkeypatch):
    from app.core.config import SETTINGS
    monkeypatch.setattr(SETTINGS, "RX_INGEST_TOKEN", "test-ingest")
    yield


# ---------------------------------------------------------------------------
# Write auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deep_post_rejects_missing_token(client):
    r = await client.post(
        "/v1/rx/deep",
        json={"kind": "deep_retrieval", "query_hash": "abc", "payload": {}},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_deep_post_rejects_bad_token(client):
    r = await client.post(
        "/v1/rx/deep",
        json={"kind": "deep_retrieval", "query_hash": "abc", "payload": {}},
        headers={"X-RX-Ingest-Token": "wrong"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Create + validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deep_post_creates_with_query_hash(client):
    from app.core.config import SETTINGS
    r = await client.post(
        "/v1/rx/deep",
        json={
            "kind": "deep_retrieval",
            "query_hash": "sha:deadbeef",
            "payload": {"candidates": [{"path": "Books/x.md", "hop": 2}]},
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "deep_retrieval"
    assert body["query_hash"] == "sha:deadbeef"
    assert body["rec_id"] is None
    assert body["payload"]["candidates"][0]["hop"] == 2
    assert body["owner_user_id"] == SETTINGS.RX_OPERATOR_UUID
    assert len(body["id"]) == 36


@pytest.mark.asyncio
async def test_governor_annotates_contradiction_on_ingest(client):
    """Phase 8: the severity governor runs at ingest + is stored in payload."""
    r = await client.post(
        "/v1/rx/deep",
        json={
            "kind": "contradiction",
            "rec_id": "rec-gov-1",
            "payload": {"contradicts_count": 2, "verdict": "conflicted"},
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    gov = r.json()["payload"]["governor"]
    assert gov["severity"] == "high"
    assert gov["raise_banner"] is True


@pytest.mark.asyncio
async def test_governor_caps_single_source_disconfirmation(client):
    r = await client.post(
        "/v1/rx/deep",
        json={
            "kind": "disconfirmation",
            "rec_id": "rec-gov-2",
            "payload": {"strength": "strong",
                        "sources": [{"publisher": "Blog", "tier": "low"}]},
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    gov = r.json()["payload"]["governor"]
    assert gov["credibility"] == "thin"  # web-surface-bias guard at ingest
    assert gov["counts_against_thesis"] is False


@pytest.mark.asyncio
async def test_deep_post_creates_with_rec_id(client):
    r = await client.post(
        "/v1/rx/deep",
        json={
            "kind": "contradiction",
            "rec_id": "11111111-1111-1111-1111-111111111111",
            "payload": {"pairs": [{"a": "s1", "b": "s2", "stance": "contradict"}]},
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    assert r.json()["rec_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_deep_post_requires_a_key(client):
    """Neither rec_id nor query_hash → 422 (schema model_validator)."""
    r = await client.post(
        "/v1/rx/deep",
        json={"kind": "deep_retrieval", "payload": {}},
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_deep_post_rejects_bad_kind(client):
    r = await client.post(
        "/v1/rx/deep",
        json={"kind": "bogus", "query_hash": "x", "payload": {}},
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 422  # Literal rejects


@pytest.mark.asyncio
async def test_deep_post_ignores_client_owner(client):
    from app.core.config import SETTINGS
    r = await client.post(
        "/v1/rx/deep",
        json={
            "kind": "disconfirmation",
            "query_hash": "x",
            "payload": {},
            "owner_user_id": "00000000-attacker-0000-0000-000000000000",
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["owner_user_id"] == SETTINGS.RX_OPERATOR_UUID


# ---------------------------------------------------------------------------
# Read auth + listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deep_get_requires_api_key(client):
    r = await client.get("/v1/rx/deep?query_hash=x")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_deep_get_requires_a_scope(client):
    """Unscoped GET (no rec_id/query_hash) → 400, can't scan the table."""
    r = await client.get("/v1/rx/deep", headers=HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_deep_roundtrip_list_by_query_hash(client):
    await client.post(
        "/v1/rx/deep",
        json={"kind": "deep_retrieval", "query_hash": "q1", "payload": {"n": 1}},
        headers=INGEST_HEADERS,
    )
    r = await client.get("/v1/rx/deep?query_hash=q1", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["payload"]["n"] == 1


@pytest.mark.asyncio
async def test_deep_list_filters_by_kind(client):
    for kind in ("deep_retrieval", "contradiction"):
        await client.post(
            "/v1/rx/deep",
            json={"kind": kind, "rec_id": "rec-xyz", "payload": {}},
            headers=INGEST_HEADERS,
        )
    r = await client.get(
        "/v1/rx/deep?rec_id=rec-xyz&kind=contradiction", headers=HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["kind"] == "contradiction"


@pytest.mark.asyncio
async def test_deep_list_validates_limit(client):
    r = await client.get("/v1/rx/deep?query_hash=x&limit=999", headers=HEADERS)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Defense-in-depth: DB CHECK on kind
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_check_rejects_bad_kind_direct_insert(client):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        async with _db.SessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO rx_deep_results "
                    "(id, owner_user_id, kind, payload, query_hash) "
                    "VALUES (:i, :o, 'bogus', '{}', 'q')"
                ),
                {"i": "22222222-2222-2222-2222-222222222222", "o": "u"},
            )
            await session.commit()
