"""Tests for ``vault_indexer.lexical`` — Phase E Commit 4.

Covers:
  - FTS5 init creates the virtual table idempotently
  - rebuild populates from current vault_chunk + vault_node
  - search returns BM25-ordered rows (best match first)
  - _sanitize_query strips FTS-special characters
  - rrf_merge fuses two lists by (path, ord)
  - Edge cases: empty query, no matches, single list
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture
def fts_con(tmp_path, monkeypatch):
    """Create a minimal cache with FTS5 + a few seeded chunks."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    for m in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[m]
    from vault_indexer import cache, lexical
    con = cache.init(tmp_path / "test.db", embedding_dim=4)
    # Seed nodes + chunks
    with cache.transaction(con) as cur:
        cache.upsert_node(
            cur, path="Books/graham/intro.md", kind="book_chapter",
            title="Intelligent Investor Intro", author="Benjamin Graham",
            published_at="1949-01-01", ingested_at=None,
            horizon_months=None, parent_path=None, tags=["investing"],
            body_hash="aaa", body_md="x", last_indexed_at="2026-05-16",
            evergreen=True,
        )
        cur.execute(
            "INSERT INTO vault_chunk (path, ord, text, section) VALUES (?, ?, ?, ?)",
            ("Books/graham/intro.md", 0,
             "Margin of safety is the central concept of investment.",
             "Chapter 1: Investment Versus Speculation"),
        )
        cache.upsert_node(
            cur, path="Videos/click-capital/2026-05-09.md", kind="video",
            title="Click Capital May 9", author="Click Capital",
            published_at="2026-05-09", ingested_at=None,
            horizon_months=24, parent_path=None, tags=["sentiment"],
            body_hash="bbb", body_md="y", last_indexed_at="2026-05-16",
            evergreen=False,
        )
        cur.execute(
            "INSERT INTO vault_chunk (path, ord, text, section) VALUES (?, ?, ?, ?)",
            ("Videos/click-capital/2026-05-09.md", 0,
             "Markets are showing extreme bearish sentiment, fear and greed index at lows.",
             "Sentiment analysis"),
        )
    return con, lexical


# ---------------------------------------------------------------------------
# Schema + populate
# ---------------------------------------------------------------------------

def test_init_fts_creates_table_idempotently(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    for m in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[m]
    from vault_indexer import cache, lexical
    con = cache.init(tmp_path / "t.db", embedding_dim=4)
    # init() already calls init_fts; calling again must not raise
    lexical.init_fts(con)
    lexical.init_fts(con)
    rows = list(con.execute(
        "SELECT name FROM sqlite_master WHERE name='vault_chunk_fts'"
    ))
    assert len(rows) == 1


def test_rebuild_populates_from_vault_chunk(fts_con):
    con, lexical = fts_con
    inserted = lexical.rebuild(con)
    assert inserted == 2
    count = list(con.execute("SELECT COUNT(*) FROM vault_chunk_fts"))[0][0]
    assert count == 2


def test_rebuild_idempotent(fts_con):
    con, lexical = fts_con
    lexical.rebuild(con)
    second = lexical.rebuild(con)
    # Second rebuild reinserts; count stays the same
    assert second == 2
    count = list(con.execute("SELECT COUNT(*) FROM vault_chunk_fts"))[0][0]
    assert count == 2


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def test_search_finds_book_chunk(fts_con):
    con, lexical = fts_con
    lexical.rebuild(con)
    results = lexical.search(con, "margin of safety", k=5)
    assert len(results) >= 1
    assert results[0]["path"] == "Books/graham/intro.md"
    assert results[0]["lexical_score"] > 0


def test_search_section_match_boosts_chunk(fts_con):
    """Query matches a chunk's section heading — should still rank highly."""
    con, lexical = fts_con
    lexical.rebuild(con)
    # "Sentiment analysis" is the section heading
    results = lexical.search(con, "sentiment analysis", k=5)
    assert any(r["path"] == "Videos/click-capital/2026-05-09.md" for r in results)


def test_search_empty_query_returns_empty(fts_con):
    con, lexical = fts_con
    lexical.rebuild(con)
    assert lexical.search(con, "", k=5) == []
    assert lexical.search(con, "   ", k=5) == []


def test_search_no_matches_returns_empty(fts_con):
    con, lexical = fts_con
    lexical.rebuild(con)
    # "quantum" doesn't appear in either seeded doc
    assert lexical.search(con, "quantum entanglement", k=5) == []


def test_search_title_match(fts_con):
    """Title content is indexed alongside body text — queries hitting the
    title rank the chunk."""
    con, lexical = fts_con
    lexical.rebuild(con)
    # "Intelligent Investor" is in the node title
    results = lexical.search(con, "intelligent investor", k=5)
    assert results[0]["path"] == "Books/graham/intro.md"


# ---------------------------------------------------------------------------
# _sanitize_query
# ---------------------------------------------------------------------------

def test_sanitize_strips_special_chars():
    from vault_indexer import lexical
    out = lexical._sanitize_query("AAPL (Q4) — earnings; revenue?")
    # All special chars removed; tokens preserved
    assert "aapl" in out
    assert "q4" in out
    assert "earnings" in out
    assert "revenue" in out
    assert "(" not in out
    assert ";" not in out


def test_sanitize_drops_short_tokens():
    from vault_indexer import lexical
    out = lexical._sanitize_query("a b cc dddd")
    assert "a" not in out.split()
    assert "b" not in out.split()
    assert "cc" in out.split()
    assert "dddd" in out.split()


def test_sanitize_empty_inputs():
    from vault_indexer import lexical
    assert lexical._sanitize_query("") == ""
    assert lexical._sanitize_query("    ") == ""
    assert lexical._sanitize_query("?!@#$%") == ""


# ---------------------------------------------------------------------------
# RRF merge
# ---------------------------------------------------------------------------

def test_rrf_merge_basic():
    from vault_indexer import lexical
    vec = [
        {"path": "a.md", "ord": 0, "text": "..."},
        {"path": "b.md", "ord": 0, "text": "..."},
    ]
    lex = [
        {"path": "b.md", "ord": 0, "lexical_score": 0.5},
        {"path": "c.md", "ord": 0, "lexical_score": 0.4},
    ]
    merged = lexical.rrf_merge(vec, lex, vector_weight=1.0, lexical_weight=1.0)
    # b appears in both → highest fused score
    assert merged[0]["path"] == "b.md"
    # All three keys represented
    paths = {m["path"] for m in merged}
    assert paths == {"a.md", "b.md", "c.md"}


def test_rrf_merge_preserves_vector_fields():
    """When an item is in both lists, the merged dict keeps the vector
    enrichment (text, section, etc.)."""
    from vault_indexer import lexical
    vec = [
        {"path": "a.md", "ord": 0, "text": "rich body", "section": "Intro"},
    ]
    lex = [
        {"path": "a.md", "ord": 0, "lexical_score": 0.8},
    ]
    merged = lexical.rrf_merge(vec, lex)
    assert merged[0]["text"] == "rich body"
    assert merged[0]["section"] == "Intro"
    assert merged[0]["lexical_score"] == 0.8
    assert "rrf_score" in merged[0]


def test_rrf_merge_lexical_weight_zero_pure_vector():
    from vault_indexer import lexical
    vec = [
        {"path": "a.md", "ord": 0, "text": "..."},
        {"path": "b.md", "ord": 0, "text": "..."},
    ]
    lex = [
        {"path": "b.md", "ord": 0, "lexical_score": 0.99},
    ]
    merged = lexical.rrf_merge(vec, lex, vector_weight=1.0, lexical_weight=0.0)
    # Vector ranking dominant; a beats b
    assert merged[0]["path"] == "a.md"


def test_rrf_merge_empty_inputs():
    from vault_indexer import lexical
    assert lexical.rrf_merge([], []) == []
    vec = [{"path": "a.md", "ord": 0}]
    assert lexical.rrf_merge(vec, []) == [
        {"path": "a.md", "ord": 0, "rrf_score": 1.0 / (60 + 0), "rank_vector": 0}
    ]


# ---------------------------------------------------------------------------
# FTS sync on chunk writes (Phase E Commit 6)
# ---------------------------------------------------------------------------

def test_sync_chunks_for_path_inserts_after_replace_chunks(fts_con):
    """cache.replace_chunks should keep FTS in step with vault_chunk."""
    con, lexical = fts_con
    from vault_indexer import cache
    lexical.rebuild(con)
    initial_fts = list(con.execute("SELECT COUNT(*) FROM vault_chunk_fts"))[0][0]
    assert initial_fts == 2

    # Add a fresh node + replace its chunks (simulates an ingest)
    with cache.transaction(con) as cur:
        cache.upsert_node(
            cur, path="Filings/AAPL/2026-q1.md", kind="filing",
            title="AAPL Q1 2026", author=None,
            published_at="2026-05-01", ingested_at=None,
            horizon_months=None, parent_path=None, tags=[],
            body_hash="ccc", body_md="z", last_indexed_at="2026-05-16",
            evergreen=False,
        )
        cache.replace_chunks(cur, "Filings/AAPL/2026-q1.md", [
            (0, "Revenue guidance for fiscal 2026 includes forward-looking statements.",
             "Risk Factors", [0.1, 0.2, 0.3, 0.4]),
        ])

    # FTS should now have the new chunk WITHOUT a separate /reload call
    post_fts = list(con.execute("SELECT COUNT(*) FROM vault_chunk_fts"))[0][0]
    assert post_fts == initial_fts + 1
    # And it should be queryable lexically right away
    results = lexical.search(con, "forward-looking revenue guidance", k=5)
    assert any(r["path"] == "Filings/AAPL/2026-q1.md" for r in results)


def test_sync_chunks_replaces_stale_fts_rows(fts_con):
    """Re-ingesting a path replaces its FTS rows (doesn't accumulate)."""
    con, lexical = fts_con
    from vault_indexer import cache
    lexical.rebuild(con)
    # Replace existing chunks on Books/graham/intro.md with new text
    with cache.transaction(con) as cur:
        cache.replace_chunks(cur, "Books/graham/intro.md", [
            (0, "Totally new content about something else entirely.",
             "Revised section", [0.5, 0.5, 0.5, 0.5]),
        ])
    # Old chunk should no longer be findable lexically
    results = lexical.search(con, "margin of safety", k=5)
    assert not any(r["path"] == "Books/graham/intro.md" for r in results)
    # New chunk should be findable
    results = lexical.search(con, "totally new content", k=5)
    assert any(r["path"] == "Books/graham/intro.md" for r in results)
    # Still exactly one row for this path (no accumulation)
    cnt = list(con.execute(
        "SELECT COUNT(*) FROM vault_chunk_fts WHERE path = ?",
        ("Books/graham/intro.md",),
    ))[0][0]
    assert cnt == 1


def test_search_with_filter_sql_constrains_to_matching_paths(fts_con):
    """Lexical leg honours anchor SQL pre-filter. AAPL query with kind=filing
    filter shouldn't surface non-filing content even if it lexically matches.
    """
    con, lexical = fts_con
    from vault_indexer import cache
    # Seed an AAPL filing + a non-filing chunk that also has 'AAPL' in body.
    with cache.transaction(con) as cur:
        cache.upsert_node(
            cur, path="Filings/AAPL/2026-q1.md", kind="filing",
            title="AAPL Q1", author=None, published_at="2026-05-01",
            ingested_at=None, horizon_months=None, parent_path=None,
            tags=[], body_hash="aapl1", body_md="x",
            last_indexed_at="2026-05-16", evergreen=False,
        )
        cache.replace_chunks(cur, "Filings/AAPL/2026-q1.md", [
            (0, "AAPL revenue guidance forward looking statements.",
             "Item 7", [0.1, 0.2, 0.3, 0.4]),
        ])
        cache.upsert_node(
            cur, path="Research/2026-05-04-aapl-thesis.md", kind="research_answer",
            title="AAPL thesis stress-test", author=None,
            published_at="2026-05-04", ingested_at=None,
            horizon_months=None, parent_path=None, tags=[],
            body_hash="rsh1", body_md="x", last_indexed_at="2026-05-16",
            evergreen=False,
        )
        cache.replace_chunks(cur, "Research/2026-05-04-aapl-thesis.md", [
            (0, "AAPL earnings narrative summary.",
             "Summary", [0.5, 0.5, 0.5, 0.5]),
        ])

    # Sanity: no filter → both match
    unfiltered = lexical.search(con, "AAPL earnings", k=10)
    paths = {r["path"] for r in unfiltered}
    assert "Filings/AAPL/2026-q1.md" in paths
    assert "Research/2026-05-04-aapl-thesis.md" in paths

    # With anchor filter for kind=filing → only the filing
    filtered = lexical.search(
        con, "AAPL earnings", k=10,
        filter_sql="n.kind IN (?)",
        filter_params=["filing"],
    )
    fp = {r["path"] for r in filtered}
    assert "Filings/AAPL/2026-q1.md" in fp
    assert "Research/2026-05-04-aapl-thesis.md" not in fp


def test_search_with_filter_uses_query_parse_build_filter_sql(fts_con):
    """End-to-end with build_filter_sql output."""
    con, lexical = fts_con
    from vault_indexer import cache, query_parse as qp
    with cache.transaction(con) as cur:
        cache.upsert_node(
            cur, path="Filings/AAPL/2026-q1.md", kind="filing",
            title="AAPL Q1", author=None, published_at="2026-05-01",
            ingested_at=None, horizon_months=None, parent_path=None,
            tags=[], body_hash="b1", body_md="x",
            last_indexed_at="2026-05-16", evergreen=False,
        )
        cache.replace_chunks(cur, "Filings/AAPL/2026-q1.md", [
            (0, "Revenue guidance for fiscal 2026.", "Item 7",
             [0.1, 0.2, 0.3, 0.4]),
        ])

    parsed = qp.ParsedQuery(tickers=["AAPL"], kinds=["filing"])
    sql, params = qp.build_filter_sql(parsed)
    results = lexical.search(
        con, "revenue guidance fiscal 2026", k=10,
        filter_sql=sql, filter_params=params,
    )
    assert any(r["path"] == "Filings/AAPL/2026-q1.md" for r in results)


def test_search_with_empty_filter_sql_no_op(fts_con):
    """filter_sql=None or empty string → behaves like unfiltered search."""
    con, lexical = fts_con
    lexical.rebuild(con)
    none_result = lexical.search(con, "margin safety", k=5, filter_sql=None)
    empty_result = lexical.search(con, "margin safety", k=5, filter_sql="")
    plain = lexical.search(con, "margin safety", k=5)
    assert {r["path"] for r in none_result} == {r["path"] for r in plain}
    assert {r["path"] for r in empty_result} == {r["path"] for r in plain}


def test_delete_node_removes_fts_rows(fts_con):
    """cache.delete_node should remove the path's FTS rows."""
    con, lexical = fts_con
    from vault_indexer import cache
    lexical.rebuild(con)
    assert list(con.execute(
        "SELECT COUNT(*) FROM vault_chunk_fts WHERE path = ?",
        ("Books/graham/intro.md",),
    ))[0][0] == 1

    with cache.transaction(con) as cur:
        cache.delete_node(cur, "Books/graham/intro.md")
    assert list(con.execute(
        "SELECT COUNT(*) FROM vault_chunk_fts WHERE path = ?",
        ("Books/graham/intro.md",),
    ))[0][0] == 0
    # Still queryable for other paths
    results = lexical.search(con, "sentiment", k=5)
    assert any(r["path"] == "Videos/click-capital/2026-05-09.md" for r in results)
