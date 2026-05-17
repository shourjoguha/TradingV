"""Tests for ``vault_indexer.query_parse`` — Phase E Commit 3.

Covers:
  - Ticker detection (lexicon-gated, no false positives on USA/GDP)
  - Kind keyword detection (alias expansion)
  - Time phrase detection (relative + month-year + year-alone)
  - raw_terms after extraction
  - SQL filter building
  - Edge cases: empty query, no lexicon, mixed signals
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def _import():
    """Fresh import (config-independent — query_parse is pure)."""
    if "vault_indexer.query_parse" in sys.modules:
        del sys.modules["vault_indexer.query_parse"]
    from vault_indexer import query_parse
    return query_parse


# ---------------------------------------------------------------------------
# Ticker detection
# ---------------------------------------------------------------------------

def test_ticker_in_lexicon_detected():
    qp = _import()
    parsed = qp.parse("AAPL earnings", ticker_lexicon={"AAPL", "MSFT"})
    assert parsed.tickers == ["AAPL"]


def test_ticker_not_in_lexicon_ignored():
    """Token shape matches but lexicon rejects → no ticker detected.

    Without this filter, `USA` / `GDP` / `CEO` would all surface as tickers.
    """
    qp = _import()
    parsed = qp.parse("USA GDP growth", ticker_lexicon={"AAPL"})
    assert parsed.tickers == []


def test_multiple_tickers_preserve_order():
    qp = _import()
    parsed = qp.parse("compare MSFT vs AAPL revenue", ticker_lexicon={"AAPL", "MSFT"})
    assert parsed.tickers == ["MSFT", "AAPL"]


def test_lowercase_token_not_ticker():
    """Operator types tickers uppercase. Lowercase `aapl` should NOT match."""
    qp = _import()
    parsed = qp.parse("aapl earnings", ticker_lexicon={"AAPL"})
    assert parsed.tickers == []


def test_no_lexicon_no_tickers():
    qp = _import()
    parsed = qp.parse("AAPL MSFT", ticker_lexicon=None)
    assert parsed.tickers == []


# ---------------------------------------------------------------------------
# Kind detection
# ---------------------------------------------------------------------------

def test_kind_simple():
    qp = _import()
    parsed = qp.parse("show me earnings calls")
    assert "filing" in parsed.kinds


def test_kind_synonym_expansion():
    """`book` expands to both `book` and `book_chapter`."""
    qp = _import()
    parsed = qp.parse("graham books")
    assert set(parsed.kinds) >= {"book", "book_chapter"}


def test_kind_case_insensitive():
    qp = _import()
    parsed = qp.parse("any TRANSCRIPTS lately")
    assert "video" in parsed.kinds


def test_kind_no_partial_match():
    """`videos` matches, but `videogaming` should not."""
    qp = _import()
    parsed = qp.parse("videogaming industry")
    assert "video" not in parsed.kinds


# ---------------------------------------------------------------------------
# Time phrase detection
# ---------------------------------------------------------------------------

def test_recent_phrase():
    qp = _import()
    today = datetime.date(2026, 5, 16)
    parsed = qp.parse("recent news", today=today)
    assert parsed.since == datetime.date(2026, 4, 16)  # 30d back


def test_last_week():
    qp = _import()
    today = datetime.date(2026, 5, 16)
    parsed = qp.parse("anything posted last week", today=today)
    assert parsed.since == datetime.date(2026, 5, 2)   # 14d back


def test_today_phrase():
    qp = _import()
    today = datetime.date(2026, 5, 16)
    parsed = qp.parse("what's today?", today=today)
    assert parsed.since == datetime.date(2026, 5, 15)


def test_month_year():
    qp = _import()
    parsed = qp.parse("May 2026 reports")
    assert parsed.since == datetime.date(2026, 5, 1)


def test_year_alone():
    qp = _import()
    parsed = qp.parse("2025 earnings season")
    assert parsed.since == datetime.date(2025, 1, 1)


def test_phrase_wins_over_year_alone():
    """Relative phrase takes priority — operator's intent is recency, not year."""
    qp = _import()
    today = datetime.date(2026, 5, 16)
    parsed = qp.parse("recent 2024 retrospective", today=today)
    assert parsed.since == datetime.date(2026, 4, 16)


# ---------------------------------------------------------------------------
# raw_terms
# ---------------------------------------------------------------------------

def test_raw_terms_excludes_consumed():
    qp = _import()
    parsed = qp.parse(
        "AAPL earnings May 2026 valuation discount",
        ticker_lexicon={"AAPL"},
        today=datetime.date(2026, 5, 16),
    )
    assert "AAPL" not in parsed.raw_terms
    assert "earnings" not in [t.lower() for t in parsed.raw_terms]
    # May 2026 consumed; "valuation discount" remains
    assert "valuation" in parsed.raw_terms
    assert "discount" in parsed.raw_terms


def test_raw_terms_no_anchors_returns_all_tokens():
    qp = _import()
    parsed = qp.parse("pure semantic question", ticker_lexicon={"AAPL"})
    assert parsed.raw_terms == ["pure", "semantic", "question"]


def test_has_anchors_false_when_empty():
    qp = _import()
    parsed = qp.parse("just words here")
    assert parsed.has_anchors() is False


def test_has_anchors_true_when_any_signal():
    qp = _import()
    parsed = qp.parse("AAPL", ticker_lexicon={"AAPL"})
    assert parsed.has_anchors() is True


# ---------------------------------------------------------------------------
# SQL filter
# ---------------------------------------------------------------------------

def test_build_filter_sql_no_anchors_empty():
    qp = _import()
    parsed = qp.ParsedQuery()
    sql, params = qp.build_filter_sql(parsed)
    assert sql == ""
    assert params == []


def test_build_filter_sql_ticker_only():
    qp = _import()
    parsed = qp.ParsedQuery(tickers=["AAPL"])
    sql, params = qp.build_filter_sql(parsed)
    assert "c.path LIKE ?" in sql
    assert "Filings/AAPL/%" in params
    assert "Research/%-AAPL-%" in params
    assert "Research/%-aapl-%" in params


def test_build_filter_sql_kind_only():
    qp = _import()
    parsed = qp.ParsedQuery(kinds=["filing"])
    sql, params = qp.build_filter_sql(parsed)
    assert "n.kind IN" in sql
    assert params == ["filing"]


def test_build_filter_sql_since_clause():
    qp = _import()
    parsed = qp.ParsedQuery(since=datetime.date(2026, 1, 1))
    sql, params = qp.build_filter_sql(parsed)
    assert "n.published_at IS NULL" in sql
    assert "n.published_at >= ?" in sql
    assert params == ["2026-01-01"]


def test_build_filter_sql_all_signals():
    qp = _import()
    parsed = qp.ParsedQuery(
        tickers=["AAPL"], kinds=["filing"], since=datetime.date(2026, 1, 1)
    )
    sql, params = qp.build_filter_sql(parsed)
    # Three AND-joined clauses
    assert sql.count(" AND ") == 2
    assert "Filings/AAPL/%" in params
    assert "filing" in params
    assert "2026-01-01" in params


# ---------------------------------------------------------------------------
# Lexicon loading
# ---------------------------------------------------------------------------

def test_load_ticker_lexicon_from_paths():
    """Build lexicon from a mock cursor returning path rows."""
    qp = _import()

    class MockCon:
        def execute(self, sql):
            return iter([
                ("Filings/AAPL/2026-05-01-10-q.md",),
                ("Filings/MSFT/2026-04-01-10-k.md",),
                ("Research/2026-05-09-aapl-wedge.md",),
                ("Research/2026-05-08-BTC-rally.md",),
                ("Filings//bogus-empty-ticker.md",),
                ("Filings/notashortname/x.md",),
                ("Notes/random.md",),  # ignored — not Filings/Research
            ])
    out = qp.load_ticker_lexicon(MockCon())
    assert "AAPL" in out
    assert "MSFT" in out
    assert "BTC" in out
    assert "" not in out
    assert "notashortname" not in out  # too long


def test_load_ticker_lexicon_empty_db():
    qp = _import()

    class MockCon:
        def execute(self, sql):
            return iter([])
    assert qp.load_ticker_lexicon(MockCon()) == set()
