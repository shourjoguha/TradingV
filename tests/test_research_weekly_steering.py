"""Steering ranker + log emitter for the weekly research loop.

The weekly loop already has integration coverage in ``test_research.py``;
this module narrowly covers the new steering-pass logic added in the
2026-05-09 free-tier follow-on plan: priority order + log file shape.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.research import weekly as _weekly


@dataclass
class _FakeHypothesis:
    slug: str
    expires_at: datetime.datetime


def _utc(year, month, day) -> datetime.datetime:
    return datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# _rank_active
# ---------------------------------------------------------------------------

def test_rank_at_risk_first_then_soonest_to_expire():
    now = _utc(2026, 5, 9)
    h_distant = _FakeHypothesis(slug="distant", expires_at=_utc(2026, 12, 1))
    h_at_risk_a = _FakeHypothesis(slug="at-risk-a", expires_at=_utc(2026, 5, 20))
    h_at_risk_b = _FakeHypothesis(slug="at-risk-b", expires_at=_utc(2026, 5, 14))
    h_no_expiry = _FakeHypothesis(slug="no-expiry", expires_at=None)  # type: ignore[arg-type]

    ranked = _weekly._rank_active(
        [h_distant, h_at_risk_a, h_at_risk_b, h_no_expiry], now=now
    )
    slugs = [h.slug for h, _ in ranked]
    # Both at-risk first, soonest first.
    assert slugs[0] == "at-risk-b"
    assert slugs[1] == "at-risk-a"
    # Then non-at-risk by days_to_expire ascending; no-expiry pushed to the end.
    assert slugs[2] == "distant"
    assert slugs[3] == "no-expiry"


def test_rank_meta_marks_at_risk_correctly():
    now = _utc(2026, 5, 9)
    h_in = _FakeHypothesis(slug="in", expires_at=_utc(2026, 5, 25))      # 16d
    h_out = _FakeHypothesis(slug="out", expires_at=_utc(2026, 7, 25))    # 77d

    ranked = _weekly._rank_active([h_in, h_out], now=now)
    meta_by_slug = {h.slug: m for h, m in ranked}
    assert meta_by_slug["in"]["is_at_risk"] is True
    assert meta_by_slug["in"]["priority_reason"] == "at_risk"
    assert meta_by_slug["out"]["is_at_risk"] is False
    assert meta_by_slug["out"]["priority_reason"] == "scheduled"
    # Days are computed against now in days.
    assert 14 <= meta_by_slug["in"]["days_to_expire"] <= 17
    assert 75 <= meta_by_slug["out"]["days_to_expire"] <= 79


def test_rank_handles_naive_datetimes_as_utc():
    """Postgres TIMESTAMPTZ vs SQLite naive — both should rank correctly."""
    now = _utc(2026, 5, 9)
    h = _FakeHypothesis(
        slug="naive", expires_at=datetime.datetime(2026, 5, 20)  # naive
    )
    ranked = _weekly._rank_active([h], now=now)
    assert ranked[0][1]["is_at_risk"] is True


# ---------------------------------------------------------------------------
# _append_to_steering_log
# ---------------------------------------------------------------------------

def test_steering_log_creates_file_and_appends_block(tmp_path, monkeypatch):
    monkeypatch.setattr(_weekly, "VAULT_PATH", tmp_path)
    started = _utc(2026, 5, 9)
    events = [
        {
            "rank": 1,
            "slug": "btc-bottom-3m",
            "priority_reason": "at_risk",
            "is_at_risk": True,
            "days_to_expire": 5,
            "started_at": started.isoformat(),
            "status": "ok",
            "verdict": "Thesis weakening; consider tightening invalidator.",
            "answer_path": "Research/abc123.md",
            "research_query_id": "abc123",
        },
        {
            "rank": 2,
            "slug": "em-breakout-12m",
            "priority_reason": "scheduled",
            "is_at_risk": False,
            "days_to_expire": 200,
            "started_at": started.isoformat(),
            "status": "error",
            "error": "Claude API timeout",
        },
    ]
    stats = {"hypotheses": 2, "ok": 1, "errors": 1, "at_risk_first": 1}
    _weekly._append_to_steering_log(
        events=events, run_started_at=started, stats=stats
    )

    log_path = tmp_path / "Research" / "_steering-log.md"
    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    # Header preamble written on first use.
    assert "# Research weekly steering log" in body
    # Section heading is the run timestamp.
    assert started.isoformat() in body
    # Summary line + at-risk count.
    assert "at_risk_first=1" in body
    # Markdown table contains rank + slug + at-risk indicator.
    assert "| 1 | `btc-bottom-3m` | at_risk | ✓ |" in body
    assert "| 2 | `em-breakout-12m` | scheduled |  |" in body
    # Error event surfaces as a warning row.
    assert "⚠ Claude API timeout" in body
    # JSON block is parseable.
    json_start = body.rindex("```json\n") + len("```json\n")
    json_end = body.rindex("\n```")
    payload = json.loads(body[json_start:json_end])
    assert payload["stats"]["hypotheses"] == 2
    assert payload["events"][0]["slug"] == "btc-bottom-3m"


def test_steering_log_appends_without_clobbering_existing_content(tmp_path, monkeypatch):
    """Two ticks in a row should produce two stacked sections, header
    written once."""
    monkeypatch.setattr(_weekly, "VAULT_PATH", tmp_path)
    for ts in (_utc(2026, 5, 9), _utc(2026, 5, 16)):
        _weekly._append_to_steering_log(
            events=[
                {
                    "rank": 1,
                    "slug": "x",
                    "priority_reason": "scheduled",
                    "is_at_risk": False,
                    "days_to_expire": 100,
                    "started_at": ts.isoformat(),
                    "status": "ok",
                    "verdict": "fine",
                }
            ],
            run_started_at=ts,
            stats={"hypotheses": 1, "ok": 1, "errors": 0, "at_risk_first": 0},
        )
    body = (tmp_path / "Research" / "_steering-log.md").read_text(encoding="utf-8")
    assert body.count("# Research weekly steering log") == 1
    assert body.count("## 2026-05-09") == 1
    assert body.count("## 2026-05-16") == 1
