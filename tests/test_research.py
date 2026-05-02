"""Tests for the Phase 3 stress-test endpoint and pieces.

Covers DSL validation, markdown rendering, bundle truncation, route
round-trip with a mocked Claude call, and approve/dismiss flow.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.research import bundle as bundle_mod
from app.research import client as client_mod
from app.research import rendering as rendering_mod
from app.research import service as service_mod

HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# DSL validation gate
# ---------------------------------------------------------------------------


def test_validate_proposed_rejects_unknown_op():
    bundle = {
        "hypotheses": [{"slug": "x"}],
        "evidence": [{"vault_path": "Notes/a.md"}],
    }
    tool_call = {
        "name": "propose_invalidator_update",
        "input": {
            "hypothesis_slug": "x",
            "rationale": "test",
            "proposed_invalidator": {"op": "fake_op", "args": {}},
            "evidence_paths": [],
            "confidence": 0.5,
        },
    }
    validated, why = service_mod._validate_proposed(tool_call, bundle)
    assert validated is None
    assert "invalid DSL" in (why or "")


def test_validate_proposed_rejects_unbundled_hypothesis():
    bundle = {"hypotheses": [{"slug": "a"}], "evidence": []}
    tool_call = {
        "name": "propose_invalidator_update",
        "input": {
            "hypothesis_slug": "b",
            "rationale": "test",
            "proposed_invalidator": {
                "op": "series_above_threshold",
                "args": {"symbol": "DXY", "threshold": 110, "days_above": 30},
            },
            "evidence_paths": [],
            "confidence": 0.5,
        },
    }
    validated, why = service_mod._validate_proposed(tool_call, bundle)
    assert validated is None
    assert "not in bundle" in (why or "")


def test_validate_proposed_rejects_unbundled_evidence_path():
    bundle = {
        "hypotheses": [{"slug": "x"}],
        "evidence": [{"vault_path": "Notes/real.md"}],
    }
    tool_call = {
        "name": "propose_invalidator_update",
        "input": {
            "hypothesis_slug": "x",
            "rationale": "test",
            "proposed_invalidator": {
                "op": "series_above_threshold",
                "args": {"symbol": "DXY", "threshold": 110, "days_above": 30},
            },
            "evidence_paths": ["Notes/halucinated.md"],
            "confidence": 0.5,
        },
    }
    validated, why = service_mod._validate_proposed(tool_call, bundle)
    assert validated is None
    assert "evidence_paths" in (why or "")


def test_validate_proposed_accepts_valid():
    bundle = {
        "hypotheses": [{"slug": "x"}],
        "evidence": [{"vault_path": "Notes/real.md"}],
    }
    tool_call = {
        "name": "propose_invalidator_update",
        "input": {
            "hypothesis_slug": "x",
            "rationale": "ok",
            "proposed_invalidator": {
                "op": "series_above_threshold",
                "args": {"symbol": "DXY", "threshold": 108, "days_above": 30},
            },
            "evidence_paths": ["Notes/real.md"],
            "confidence": 0.7,
        },
    }
    validated, why = service_mod._validate_proposed(tool_call, bundle)
    assert validated is not None
    assert why is None


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _mk_bundle():
    return {
        "query": "what's at risk?",
        "hypotheses": [
            {
                "slug": "btc-bottom-3m",
                "title": "BTC bottom",
                "claim_type": "regime",
                "axis": "btc",
                "status": "active",
                "expires_at": "2026-08-01T00:00:00Z",
                "primary_metric": "BTC-USD",
                "tracking_signal": "BTC-USD",
                "invalidator": {
                    "op": "series_above_threshold",
                    "args": {"symbol": "DX-Y.NYB", "threshold": 110, "days_above": 30},
                },
                "recent_evaluations": [],
                "linked_vault_paths": [],
            }
        ],
        "evidence": [
            {"vault_path": "Newsletters/lyn-alden/2026-w19.md", "score": 0.78, "text": "USD bid"}
        ],
        "macro_state": {"DX-Y.NYB": {"latest": 109.4, "latest_ts": "2026-05-01"}},
    }


def test_render_with_proposed_action_includes_checkbox():
    bundle = _mk_bundle()
    proposed = {
        "hypothesis_slug": "btc-bottom-3m",
        "rationale": "DXY trending higher",
        "proposed_invalidator": {
            "op": "series_above_threshold",
            "args": {"symbol": "DX-Y.NYB", "threshold": 108, "days_above": 30},
        },
        "evidence_paths": ["Newsletters/lyn-alden/2026-w19.md"],
        "confidence": 0.7,
    }
    body = rendering_mod.render(
        query=bundle["query"],
        bundle=bundle,
        verdict_text="Thesis weakening.",
        proposed_action=proposed,
        tokens_in=1000,
        tokens_out=200,
        est_cost_usd=0.012,
        research_query_id="abc-123",
        asked_at=datetime.datetime(2026, 5, 2, 12, 0, tzinfo=datetime.timezone.utc),
    )
    assert "Stress-test: btc-bottom-3m" in body
    assert "[ ] **Approve:**" in body
    assert "DX-Y.NYB" in body
    assert "research_query_id: abc-123" in body
    assert "tokens_in: 1000" in body


def test_render_without_proposed_action_says_none():
    bundle = _mk_bundle()
    body = rendering_mod.render(
        query=bundle["query"],
        bundle=bundle,
        verdict_text="No change needed.",
        proposed_action=None,
        tokens_in=900,
        tokens_out=100,
        est_cost_usd=0.005,
        research_query_id="abc-456",
        asked_at=datetime.datetime(2026, 5, 2, 12, 0, tzinfo=datetime.timezone.utc),
    )
    assert "No change needed." in body
    assert "**Approve:**" not in body
    assert "evidence does not support" in body


def test_answer_filename_uses_date_and_slug():
    fn = rendering_mod.answer_filename(
        "btc-bottom-3m",
        datetime.datetime(2026, 5, 2, 12, 0, tzinfo=datetime.timezone.utc),
    )
    assert fn == "2026-05-02-btc-bottom-3m.md"


# ---------------------------------------------------------------------------
# Bundle truncation
# ---------------------------------------------------------------------------


def test_bundle_truncation_drops_oldest_evaluations_first():
    # Make the bundle's word-count clearly exceed the cap so the loop runs.
    bundle = {
        "hypotheses": [
            {
                "slug": "x",
                "recent_evaluations": [
                    {"i": i, "blob": " ".join(["lorem"] * 50)} for i in range(5)
                ],
            }
        ],
        "evidence": [
            {
                "vault_path": f"Notes/{i}.md",
                "score": 0.9 - i * 0.05,
                "text": " ".join(["ipsum"] * 50),
            }
            for i in range(5)
        ],
    }
    before_evals = len(bundle["hypotheses"][0]["recent_evaluations"])
    trimmed = bundle_mod._truncate(bundle, cap_tokens=80)
    after_evals = len(trimmed["hypotheses"][0]["recent_evaluations"])
    assert after_evals < before_evals  # at least some evaluations got dropped
    assert after_evals == 1  # truncation pops down to one


# ---------------------------------------------------------------------------
# Cost calc
# ---------------------------------------------------------------------------


def test_cost_calc_default_pricing(monkeypatch):
    # Force defaults.
    for env in [
        "CLAUDE_INPUT_COST_PER_MTOK",
        "CLAUDE_OUTPUT_COST_PER_MTOK",
        "CLAUDE_CACHE_READ_COST_PER_MTOK",
    ]:
        monkeypatch.delenv(env, raising=False)
    cost = client_mod._calc_cost(tokens_in=1_000_000, tokens_out=500_000, cache_read=0)
    assert cost == pytest.approx(3.0 + 7.5)


# ---------------------------------------------------------------------------
# Route round-trip with mocked Claude
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_route_round_trip(client, tmp_path, monkeypatch):
    """End-to-end: seed a hypothesis, mock Claude, fire /ask, assert the
    answer file lands and the row persists."""
    from app.hypotheses.schemas import HypothesisCreate
    from app.research import service as svc

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    # service.VAULT_PATH was bound at import; override it directly.
    monkeypatch.setattr(svc, "VAULT_PATH", tmp_path)

    create_resp = await client.post(
        "/v1/hypotheses",
        headers=HEADERS,
        json={
            "slug": "btc-bottom-3m",
            "title": "BTC bottom",
            "claim_type": "regime",
            "axis": "btc",
            "primary_metric": "BTC-USD",
            "tracking_signal": "BTC-USD",
            "invalidator": {
                "op": "series_above_threshold",
                "args": {"symbol": "DX-Y.NYB", "threshold": 110, "days_above": 30},
            },
            "ttl_months": 3,
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    # Mock the Claude call.
    fake = client_mod.ClaudeResult(
        verdict_text="Thesis weakening — DXY trending up.",
        tool_calls=[
            {
                "id": "tu_1",
                "name": "propose_invalidator_update",
                "input": {
                    "hypothesis_slug": "btc-bottom-3m",
                    "rationale": "DXY persistence",
                    "proposed_invalidator": {
                        "op": "series_above_threshold",
                        "args": {"symbol": "DX-Y.NYB", "threshold": 108, "days_above": 30},
                    },
                    "evidence_paths": [],
                    "confidence": 0.65,
                },
            }
        ],
        tokens_in=2000,
        tokens_out=500,
        cache_read_tokens=0,
        est_cost_usd=0.012,
    )

    async def _fake_ask_claude(**kwargs):
        return fake

    monkeypatch.setattr(svc._client, "ask_claude", _fake_ask_claude)

    # Bypass the vault-indexer HTTP call — not running in tests.
    async def _fake_evidence(*args, **kwargs):
        return []
    from app.research import bundle as bundle_mod_local
    monkeypatch.setattr(bundle_mod_local, "_retrieve_evidence", _fake_evidence)

    r = await client.post(
        "/v1/research/ask",
        headers=HEADERS,
        json={"query": "what's at risk?", "hypothesis_slugs": ["btc-bottom-3m"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["answer_path"].startswith("Research/")
    assert body["proposed_action"]["proposed_invalidator"]["args"]["threshold"] == 108

    answer = (tmp_path / body["answer_path"]).read_text(encoding="utf-8")
    assert "Stress-test: btc-bottom-3m" in answer
    assert "[ ] **Approve:**" in answer

    # Approve.
    qid = body["query_id"]
    r2 = await client.post(f"/v1/research/queries/{qid}/approve", headers=HEADERS)
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    # Verify hypothesis row was patched.
    g = await client.get("/v1/hypotheses?status=active", headers=HEADERS)
    items = g.json()["items"]
    bbm = [h for h in items if h["slug"] == "btc-bottom-3m"][0]
    assert bbm["invalidator"]["args"]["threshold"] == 108

    # Idempotent re-approve.
    r3 = await client.post(f"/v1/research/queries/{qid}/approve", headers=HEADERS)
    assert r3.status_code == 200
    assert r3.json()["status"] == "already_approved"


@pytest.mark.asyncio
async def test_ask_route_dismiss(client, tmp_path, monkeypatch):
    from app.research import service as svc

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(svc, "VAULT_PATH", tmp_path)

    await client.post(
        "/v1/hypotheses",
        headers=HEADERS,
        json={
            "slug": "ah",
            "title": "ah",
            "claim_type": "regime",
            "axis": "x",
            "primary_metric": "y",
            "tracking_signal": "y",
            "invalidator": {"op": "manual", "args": {}},
            "ttl_months": 6,
        },
    )

    fake = client_mod.ClaudeResult(
        verdict_text="No change.",
        tool_calls=[],
        tokens_in=100, tokens_out=50, cache_read_tokens=0, est_cost_usd=0.001,
    )

    async def _fake_ask_claude(**kwargs):
        return fake

    monkeypatch.setattr(svc._client, "ask_claude", _fake_ask_claude)

    async def _fake_evidence(*args, **kwargs):
        return []
    from app.research import bundle as bundle_mod_local
    monkeypatch.setattr(bundle_mod_local, "_retrieve_evidence", _fake_evidence)

    r = await client.post(
        "/v1/research/ask",
        headers=HEADERS,
        json={"query": "stress", "hypothesis_slugs": ["ah"]},
    )
    qid = r.json()["query_id"]

    r2 = await client.post(f"/v1/research/queries/{qid}/dismiss", headers=HEADERS)
    assert r2.status_code == 200
    g = await client.get(f"/v1/research/queries/{qid}", headers=HEADERS)
    assert g.json()["status"] == "dismissed"


# ---------------------------------------------------------------------------
# Vault-indexer research_hook
# ---------------------------------------------------------------------------


def test_research_hook_detects_approve_tick():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    for m in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[m]
    from vault_indexer import research_hook

    text = (
        "---\nresearch_query_id: abc-123\n---\n"
        "## Proposed action\n\n"
        "- [x] **Approve:** update foo invalidator\n"
        "  - Op: `series_above_threshold`\n"
    )
    assert research_hook._detect_tick(text) == "approve"


def test_research_hook_skips_already_applied():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    for m in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[m]
    from vault_indexer import research_hook

    text = (
        "- [x] **Approve:** ...\n"
        "<!-- vault-indexer:applied -->\n"
    )
    assert research_hook._detect_tick(text) is None
