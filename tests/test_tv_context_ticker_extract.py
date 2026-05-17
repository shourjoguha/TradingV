"""Tests for app.tv_context.ticker_extract — OCR ticker auto-extraction.

No real pytesseract or PIL invocation; both patched at module level so CI
is fast + portable. Asserts ranking rules (whitelist > stoplist-passed;
leading > anywhere; preserves first-seen order; dedupes).
"""
from __future__ import annotations

from unittest.mock import patch

from app.tv_context import ticker_extract as te


def _patch_ocr(text: str):
    """Return a context manager that patches _ocr_image to return `text`."""
    return patch.object(te, "_ocr_image", return_value=text)


def _patch_whitelist(symbols: set[str]):
    return patch.object(te, "load_ticker_whitelist_sync", return_value=symbols)


# ---------------------------------------------------------------------------
# Empty / failure paths
# ---------------------------------------------------------------------------


def test_extract_returns_empty_when_ocr_blank() -> None:
    with _patch_ocr(""), _patch_whitelist({"AAPL", "NVDA"}):
        result = te.extract_candidates(b"<bytes>")
    assert result == {"candidates": [], "ocr_used": False}


def test_extract_returns_empty_when_image_bytes_empty() -> None:
    # OCR helper returns "" for unreadable bytes — same as blank text.
    with _patch_ocr(""):
        result = te.extract_candidates(b"")
    assert result["ocr_used"] is False
    assert result["candidates"] == []


# ---------------------------------------------------------------------------
# Ranking — whitelist > stoplist-passed; leading > anywhere
# ---------------------------------------------------------------------------


def test_whitelist_leading_outranks_anywhere() -> None:
    """Whitelist hit at line-leading position ranks first."""
    text = "NVDA Daily Chart\nSome body text mentioning AAPL too"
    with _patch_ocr(text), _patch_whitelist({"AAPL", "NVDA"}):
        result = te.extract_candidates(b"<bytes>")
    cands = result["candidates"]
    assert result["ocr_used"] is True
    assert cands[0] == {"ticker": "NVDA", "source": "whitelist", "position": "leading"}
    assert cands[1] == {"ticker": "AAPL", "source": "whitelist", "position": "anywhere"}


def test_whitelist_outranks_stoplist_passed() -> None:
    """A leading non-whitelist token still ranks BELOW a whitelist token
    appearing anywhere."""
    text = "PLTR leading hit\nSomewhere AAPL appears"
    with _patch_ocr(text), _patch_whitelist({"AAPL"}):
        result = te.extract_candidates(b"<bytes>")
    cands = result["candidates"]
    # AAPL (whitelist anywhere) → first; PLTR (stoplist-passed leading) → second
    assert cands[0]["ticker"] == "AAPL"
    assert cands[0]["source"] == "whitelist"
    assert cands[1]["ticker"] == "PLTR"
    assert cands[1]["source"] == "stoplist-passed"


def test_stoplist_filters_acronyms_even_without_whitelist() -> None:
    """Static stoplist (AI/USA/GDP/etc.) drops noise even when whitelist empty."""
    text = "AI revolution USA GDP rising CEO speaks"
    with _patch_ocr(text), _patch_whitelist(set()):
        result = te.extract_candidates(b"<bytes>")
    tickers = [c["ticker"] for c in result["candidates"]]
    for noise in ("AI", "USA", "GDP", "CEO"):
        assert noise not in tickers


def test_stoplist_passed_when_whitelist_empty() -> None:
    """A real-looking ticker NOT in stoplist passes through when whitelist
    empty (operator may want to add a new symbol to roster)."""
    text = "PLTR Q3 earnings beat"
    with _patch_ocr(text), _patch_whitelist(set()):
        result = te.extract_candidates(b"<bytes>")
    cands = result["candidates"]
    assert len(cands) == 1
    assert cands[0]["ticker"] == "PLTR"
    assert cands[0]["source"] == "stoplist-passed"


# ---------------------------------------------------------------------------
# Dedupe + ordering
# ---------------------------------------------------------------------------


def test_extract_dedupes_repeats() -> None:
    """Same ticker mentioned 3 times → emits once."""
    text = "NVDA NVDA NVDA again and again"
    with _patch_ocr(text), _patch_whitelist({"NVDA"}):
        result = te.extract_candidates(b"<bytes>")
    nvda_hits = [c for c in result["candidates"] if c["ticker"] == "NVDA"]
    assert len(nvda_hits) == 1


def test_extract_preserves_first_seen_order_within_tier() -> None:
    """Within whitelist-leading tier, preserve OCR-order of first appearance."""
    text = "META first\nGOOGL second\nNVDA third"
    with _patch_ocr(text), _patch_whitelist({"META", "GOOGL", "NVDA"}):
        result = te.extract_candidates(b"<bytes>")
    order = [c["ticker"] for c in result["candidates"]]
    assert order == ["META", "GOOGL", "NVDA"]


def test_extract_respects_limit() -> None:
    """Caller can cap output to N candidates."""
    text = "AAPL one\nNVDA two\nMETA three\nMSFT four\nGOOGL five"
    with _patch_ocr(text), _patch_whitelist({"AAPL", "NVDA", "META", "MSFT", "GOOGL"}):
        result = te.extract_candidates(b"<bytes>", limit=2)
    assert len(result["candidates"]) == 2


# ---------------------------------------------------------------------------
# Realistic scenario
# ---------------------------------------------------------------------------


def test_realistic_tradingview_screenshot() -> None:
    """OCR output approximating a real TradingView chart screenshot."""
    text = (
        "NVDA - NVIDIA Corporation - NASDAQ\n"
        "4H 1D 1W 1M\n"
        "$485.50 +2.3%\n"
        "Volume: 32.5M\n"
        "Some chart annotations referencing CEO Jensen Huang and the AI boom\n"
        "Compared to AAPL and MSFT performance\n"
    )
    with _patch_ocr(text), _patch_whitelist({"NVDA", "AAPL", "MSFT"}):
        result = te.extract_candidates(b"<bytes>")
    cands = result["candidates"]
    # NVDA at leading position → top
    assert cands[0]["ticker"] == "NVDA"
    assert cands[0]["position"] == "leading"
    # AAPL + MSFT anywhere
    rest = [c["ticker"] for c in cands[1:]]
    assert "AAPL" in rest
    assert "MSFT" in rest
    # Noise filtered
    assert all(c["ticker"] not in {"CEO", "AI"} for c in cands)
