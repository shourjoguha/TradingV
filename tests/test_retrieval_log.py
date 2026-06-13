"""Retrieval log — the measurement substrate (retrieval-depth Phase 0).

Tests the ``tools.vault_indexer.retrieval_log`` module in isolation against a
stdlib sqlite3 connection. The module deliberately depends only on stdlib
(it takes any DB-API ``con`` with ``.cursor().execute()``), so these tests run
without apsw, sqlite-vec, or the bge model — the heavy indexer deps.

Gate evidence for Phase 0: the log makes the eligible-but-not-surfaced delta
(limitation C1) visible and persists per-candidate drop reasons; the row cap
prunes oldest.
"""
from __future__ import annotations

import sqlite3

from tools.vault_indexer import retrieval_log


def _con() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def test_ensure_schema_idempotent():
    con = _con()
    retrieval_log.ensure_schema(con)
    retrieval_log.ensure_schema(con)  # second call must not raise
    rows = list(
        con.cursor().execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='retrieval_log'"
        )
    )
    assert rows, "retrieval_log table should exist"


def test_record_and_recent_roundtrip(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_LOG_ENABLED", "1")
    con = _con()
    surfaced = [
        {"path": "Books/intelligent-investor.md", "ord": 0,
         "score": 0.81, "similarity": 0.81},
    ]
    dropped = [
        {"path": "Filings/AAPL/2024-10k.md", "ord": 2,
         "score": 0.44, "reason": "below_top_k"},
    ]
    retrieval_log.record(
        con, query="AAPL services margin", mode="fast", domain="finance",
        k=8, anchors={"tickers": ["AAPL"], "kinds": [], "since": None},
        eligible_count=5, surfaced=surfaced, dropped=dropped,
    )
    rec = retrieval_log.recent(con, limit=1)
    assert len(rec) == 1
    r = rec[0]
    assert r["query"] == "AAPL services margin"
    assert r["mode"] == "fast"
    assert r["domain"] == "finance"
    assert r["eligible_count"] == 5
    assert r["surfaced_count"] == 1
    assert r["dropped"][0]["reason"] == "below_top_k"
    assert r["dropped"][0]["path"] == "Filings/AAPL/2024-10k.md"
    assert r["anchors"]["tickers"] == ["AAPL"]


def test_eligible_exceeds_surfaced_delta_is_visible(monkeypatch):
    """The core C1-breaking property: 'had it, didn't surface' is recorded."""
    monkeypatch.setenv("RETRIEVAL_LOG_ENABLED", "1")
    con = _con()
    surfaced = [{"path": "a", "ord": 0, "score": 0.9, "similarity": 0.9}]
    dropped = [
        {"path": "b", "ord": 0, "score": 0.5, "reason": "below_top_k"},
        {"path": "c", "ord": 1, "score": 0.4, "reason": "below_top_k"},
    ]
    retrieval_log.record(
        con, query="q", mode="fast", domain="finance", k=1,
        eligible_count=3, surfaced=surfaced, dropped=dropped,
    )
    r = retrieval_log.recent(con, limit=1)[0]
    assert r["eligible_count"] > r["surfaced_count"]
    assert len(r["dropped"]) == 2


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_LOG_ENABLED", "0")
    con = _con()
    retrieval_log.record(
        con, query="q", mode="fast", domain="finance", k=8,
        eligible_count=1, surfaced=[], dropped=[],
    )
    # recent() lazily creates the schema, then finds nothing logged.
    assert retrieval_log.recent(con, limit=10) == []


def test_prune_caps_rows(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_LOG_ENABLED", "1")
    con = _con()
    for i in range(20):
        retrieval_log.record(
            con, query=f"q{i}", mode="fast", domain="finance", k=8,
            eligible_count=1, surfaced=[], dropped=[], max_rows=5,
        )
    rec = retrieval_log.recent(con, limit=100)
    assert len(rec) == 5
    # Newest retained, oldest pruned.
    assert rec[0]["query"] == "q19"
    assert all(r["query"] != "q0" for r in rec)


def test_deep_mode_label_persists(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_LOG_ENABLED", "1")
    con = _con()
    retrieval_log.record(
        con, query="q", mode="deep", domain="finance", k=50,
        eligible_count=120, surfaced=[{"path": "x", "ord": 0, "score": 0.7}],
        dropped=[{"path": "y", "ord": 0, "reason": "prune_floor", "score": 0.2}],
    )
    r = retrieval_log.recent(con, limit=1)[0]
    assert r["mode"] == "deep"
    assert r["dropped"][0]["reason"] == "prune_floor"
