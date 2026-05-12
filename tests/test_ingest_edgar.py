"""Tests for SEC EDGAR ingestor.

Mocks every outbound HTTP call so the suite runs offline and stays
deterministic. Coverage: ticker→CIK lookup with cache, atom parsing,
idempotent vault writes, polite-UA enforcement, form-type filtering,
since-date filtering.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from tools.vault_indexer.ingest import ingest_edgar as edgar


HEADERS = {"X-API-Key": "test-key"}


COMPANY_TICKERS_FIXTURE = json.dumps(
    {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1326801, "ticker": "META", "title": "Meta Platforms"},
        "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    }
)


ATOM_FIXTURE = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>EDGAR Filings</title>
  <entry>
    <title>8-K - Apple Inc. (0000320193) (Filer)</title>
    <updated>2026-01-15T16:30:00-04:00</updated>
    <link href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK=0000320193&amp;type=8-K&amp;dateb=&amp;owner=include&amp;count=40"/>
    <summary type="html">Acc-No: 0000320193-26-000005 — Filed: 2026-01-15</summary>
  </entry>
  <entry>
    <title>10-Q - Apple Inc. (0000320193) (Filer)</title>
    <updated>2025-11-02T20:00:00-04:00</updated>
    <link href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK=0000320193&amp;type=10-Q"/>
    <summary type="html">Acc-No: 0000320193-25-000098</summary>
  </entry>
  <entry>
    <title>SC 13G/A - Vanguard (Filer)</title>
    <updated>2025-10-10T09:00:00-04:00</updated>
    <link href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK=0000320193&amp;type=SC+13G%2FA"/>
    <summary type="html">Acc-No: 0001234567-25-000001</summary>
  </entry>
</feed>
"""


INDEX_JSON_FIXTURE = json.dumps(
    {
        "directory": {
            "item": [
                {"name": "0000320193-26-000005-index.htm", "type": "text"},
                {"name": "aapl-20260115.htm", "type": "text"},
                {"name": "exhibit99-1.htm", "type": "text"},
                {"name": "Financial_Report.xlsx", "type": "data"},
            ]
        }
    }
)


PRIMARY_DOC_HTML = """<!DOCTYPE html>
<html>
<head><title>Apple Inc. Q1 2026 Earnings Release</title></head>
<body>
<h1>Apple Inc. Reports First Quarter Results</h1>
<p>CUPERTINO, CALIFORNIA - Apple today announced financial results for its
fiscal 2026 first quarter ended December 28, 2025. The Company posted
quarterly revenue of $124.3 billion, up 4 percent year over year.</p>
<p>"We are pleased to report a strong start to fiscal 2026," said Tim Cook,
Apple's CEO.</p>
<blockquote>Quarterly earnings per diluted share of $2.40, up 7 percent year
over year.</blockquote>
</body>
</html>
""".encode("utf-8")


# ---------------------------------------------------------------------------
# HTTP mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_http(monkeypatch, tmp_path):
    """Patch ``edgar._http_get`` to return per-URL fixtures.

    Also patches the cache path to live under tmp_path so tests don't
    pollute the real vault.
    """
    monkeypatch.setattr(edgar, "_ticker_cache_path", lambda: tmp_path / "cik_cache.json")
    monkeypatch.setenv("EDGAR_USER_AGENT", "test-suite/1.0 test@example.com")

    calls: list[str] = []

    def _fake_http_get(url: str, *, timeout: int = 30) -> bytes:
        calls.append(url)
        if "company_tickers.json" in url:
            return COMPANY_TICKERS_FIXTURE.encode("utf-8")
        if "browse-edgar" in url:
            return ATOM_FIXTURE.encode("utf-8")
        if url.endswith("index.json"):
            return INDEX_JSON_FIXTURE.encode("utf-8")
        if url.endswith(".htm") or url.endswith(".html"):
            return PRIMARY_DOC_HTML
        raise AssertionError(f"unexpected http call: {url}")

    monkeypatch.setattr(edgar, "_http_get", _fake_http_get)
    return calls


# ---------------------------------------------------------------------------
# Polite-UA guard
# ---------------------------------------------------------------------------

def test_user_agent_required(monkeypatch):
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="EDGAR_USER_AGENT"):
        edgar._user_agent()


def test_user_agent_returns_env_value(monkeypatch):
    monkeypatch.setenv("EDGAR_USER_AGENT", "ua/1.0 me@here.com")
    assert edgar._user_agent() == "ua/1.0 me@here.com"


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

def test_resolve_cik_zero_pads_to_10_digits(mock_http):
    assert edgar.resolve_cik("AAPL") == "0000320193"
    assert edgar.resolve_cik("meta") == "0001326801"
    assert edgar.resolve_cik("ZZZZ") is None


def test_ticker_cache_persists(tmp_path, mock_http):
    edgar.resolve_cik("AAPL")
    cache_calls = sum(1 for u in mock_http if "company_tickers.json" in u)
    assert cache_calls == 1
    edgar.resolve_cik("META")  # second call should hit cache, not http
    cache_calls_after = sum(1 for u in mock_http if "company_tickers.json" in u)
    assert cache_calls_after == 1


# ---------------------------------------------------------------------------
# Atom parser
# ---------------------------------------------------------------------------

def test_parse_atom_extracts_known_filings():
    entries = edgar.parse_atom(ATOM_FIXTURE.encode("utf-8"))
    forms = [e.form_type for e in entries]
    assert "8-K" in forms
    assert "10-Q" in forms
    eight_k = next(e for e in entries if e.form_type == "8-K")
    assert eight_k.accession_number == "0000320193-26-000005"
    assert eight_k.filed_at == datetime.date(2026, 1, 15)


def test_parse_atom_handles_malformed_xml():
    assert edgar.parse_atom(b"<<not xml>>") == []


# ---------------------------------------------------------------------------
# Primary doc URL discovery
# ---------------------------------------------------------------------------

def test_primary_doc_url_skips_index_htm_picks_data_doc(mock_http):
    url = edgar._primary_doc_url("0000320193-26-000005", "0000320193")
    # Manifest contains:
    #   0000320193-26-000005-index.htm  (SEC metadata page — skip)
    #   aapl-20260115.htm                (← primary doc, what we want)
    #   exhibit99-1.htm
    # Picker should land on the data doc, not the index.
    assert url is not None
    assert url.endswith("aapl-20260115.htm")
    assert "-index.htm" not in url


def test_fetch_filing_text_returns_title_and_body(mock_http):
    out = edgar.fetch_filing_text("0000320193-26-000005", "0000320193")
    assert out is not None
    title, body = out
    assert "Apple" in title
    assert "fiscal 2026" in body
    assert "Tim Cook" in body


# ---------------------------------------------------------------------------
# End-to-end ingest_ticker
# ---------------------------------------------------------------------------

def test_ingest_ticker_writes_filings(tmp_path, mock_http):
    out = edgar.ingest_ticker(
        ticker="AAPL",
        vault_root=tmp_path,
        form_types=["8-K"],
        max_per_form=5,
    )
    assert out["ticker"] == "AAPL"
    assert out["cik"] == "0000320193"
    assert out["written"] >= 1
    paths = out["written_paths"]
    assert any("Filings/AAPL" in p for p in paths)
    # Verify the filing markdown landed with the expected frontmatter.
    folder = tmp_path / "Filings" / "AAPL"
    assert folder.is_dir()
    md_files = list(folder.glob("*.md"))
    assert md_files
    body = md_files[0].read_text()
    assert "form_type: 8-K" in body
    assert "ticker: AAPL" in body
    assert "accession_number: 0000320193-26-000005" in body


def test_ingest_ticker_idempotent(tmp_path, mock_http):
    """Second run must skip filings already present (matched on accession)."""
    edgar.ingest_ticker(
        ticker="AAPL", vault_root=tmp_path, form_types=["8-K"], max_per_form=5
    )
    second = edgar.ingest_ticker(
        ticker="AAPL", vault_root=tmp_path, form_types=["8-K"], max_per_form=5
    )
    assert second["written"] == 0
    assert second["skipped"] >= 1


def test_ingest_ticker_unknown_returns_error(tmp_path, mock_http):
    out = edgar.ingest_ticker(ticker="ZZZZ", vault_root=tmp_path)
    assert out == {"ticker": "ZZZZ", "error": "unknown_ticker"}


def test_ingest_ticker_unsupported_form_warns_and_skips(tmp_path, mock_http, caplog):
    out = edgar.ingest_ticker(
        ticker="AAPL",
        vault_root=tmp_path,
        form_types=["SC 13G", "8-K"],
        max_per_form=5,
    )
    # SC 13G silently skipped with a log; 8-K still ingested.
    assert out["written"] >= 1
    assert any("SC 13G" in r.message or "not supported" in r.message for r in caplog.records)


def test_ingest_ticker_since_filter(tmp_path, mock_http):
    # since 2025-12-31 should keep the 8-K (Jan 2026), drop the 10-Q (Nov 2025).
    out = edgar.ingest_ticker(
        ticker="AAPL",
        vault_root=tmp_path,
        form_types=["8-K", "10-Q"],
        since=datetime.date(2025, 12, 31),
        max_per_form=5,
    )
    folder = tmp_path / "Filings" / "AAPL"
    forms = []
    for md in folder.glob("*.md"):
        body = md.read_text()
        for line in body.splitlines():
            if line.startswith("form_type:"):
                forms.append(line.split(":", 1)[1].strip())
                break
    assert "8-K" in forms
    assert "10-Q" not in forms


# ---------------------------------------------------------------------------
# Bulk
# ---------------------------------------------------------------------------

def test_ingest_tickers_continues_on_failure(tmp_path, mock_http):
    out = edgar.ingest_tickers(
        ["AAPL", "ZZZZ", "META"],
        vault_root=tmp_path,
        form_types=["8-K"],
        max_per_form=5,
    )
    assert len(out) == 3
    by_ticker = {r["ticker"]: r for r in out}
    assert "error" in by_ticker["ZZZZ"]
    assert by_ticker["AAPL"]["written"] >= 1
