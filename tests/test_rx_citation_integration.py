"""Citation verification end-to-end through rx ingest (Phase 2).

Confirms the deterministic verifier runs at POST /v1/rx/recs, annotates
source_refs, and surfaces `citations_status` on both the detail and list
read models — without blocking ingest on a verifier issue.
"""
from __future__ import annotations

import pytest


HEADERS = {"X-API-Key": "test-key"}
INGEST_HEADERS = {"X-RX-Ingest-Token": "test-ingest"}


@pytest.fixture(autouse=True)
def _set_ingest_token(monkeypatch):
    from app.core.config import SETTINGS
    monkeypatch.setattr(SETTINGS, "RX_INGEST_TOKEN", "test-ingest")
    yield


@pytest.mark.asyncio
async def test_ingest_verifies_good_citation(client):
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "Trim NVDA into strength",
            "source_refs": [
                {"path": "Books/x.md", "quote": "margin of safety always",
                 "text": "the rule is margin of safety always; never overpay"},
            ],
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["citations_status"] == "all_verified"
    assert body["source_refs"][0]["citation_verified"] is True


@pytest.mark.asyncio
async def test_ingest_flags_fabricated_citation(client):
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "Add to position on guidance",
            "source_refs": [
                {"path": "Filings/aapl.md",
                 "quote": "management guided revenue up 30 percent",
                 "text": "revenue was roughly flat; no forward guidance given"},
            ],
        },
        headers=INGEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["citations_status"] == "has_mismatch"
    assert body["source_refs"][0]["citation_verified"] is False
    assert body["source_refs"][0]["citation_reason"] == "not_found"


@pytest.mark.asyncio
async def test_citations_status_on_list(client):
    await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "x",
            "source_refs": [
                {"path": "a.md", "quote": "invented span absent entirely",
                 "text": "completely unrelated chunk content"},
            ],
        },
        headers=INGEST_HEADERS,
    )
    r = await client.get("/v1/rx/recs", headers=HEADERS)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["citations_status"] == "has_mismatch"


@pytest.mark.asyncio
async def test_no_quotes_status_when_refs_lack_quotes(client):
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "x",
            "source_refs": [{"path": "a.md", "score": 0.7}],
        },
        headers=INGEST_HEADERS,
    )
    assert r.json()["citations_status"] == "no_quotes"


@pytest.mark.asyncio
async def test_unverifiable_when_no_chunk_text(client):
    r = await client.post(
        "/v1/rx/recs",
        json={
            "domain": "finance",
            "tldr": "x",
            "source_refs": [{"path": "a.md", "quote": "a real quote but no source text"}],
        },
        headers=INGEST_HEADERS,
    )
    assert r.json()["citations_status"] == "unverifiable"
