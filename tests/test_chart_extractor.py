"""Tests for tools.vault_indexer.ingest.chart_extractor — heuristic + whitelist.

No DB / no MLX. Pure regex + set logic. Whitelist loader tested via mocks.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tools.vault_indexer.ingest import chart_extractor as ce


# ---------------------------------------------------------------------------
# Heuristic chart_type detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Candlestick chart of BTC", "candlestick"),
        ("A candle chart", "candlestick"),
        ("Line chart of NASDAQ", "line"),
        ("A bar chart showing GDP", "bar"),
        ("Area graph of M2 supply", "area"),
        ("Fear and Greed Gauge at 67", "gauge"),
        ("Scatter plot of returns", "scatter"),
        ("Pie chart of allocations", "pie"),
        ("A histogram of returns", "histogram"),
        ("Just a talking head shot", None),
        ("", None),
    ],
)
def test_chart_type_regex(text: str, expected: str | None) -> None:
    assert ce.extract_from_caption(text)["chart_type"] == expected


# ---------------------------------------------------------------------------
# Heuristic timeframe detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4H candlestick chart", "4h"),
        ("The 4-hour timeframe", "4h"),
        ("Four-hour chart of BTC", "4h"),
        ("Daily candle chart", "1d"),
        ("1D candlestick", "1d"),
        ("Weekly line chart", "1w"),
        ("Monthly chart", "1mo"),
        ("3-month timeframe", "3mo"),
        ("Quarterly view", "3mo"),
        ("Yearly chart", "1y"),
        ("5-year history", "5y"),
        ("15-minute chart", "15m"),
        ("30m timeframe", "30m"),
        ("Static talking head", None),
    ],
)
def test_timeframe_regex(text: str, expected: str | None) -> None:
    assert ce.extract_from_caption(text)["timeframe"] == expected


# ---------------------------------------------------------------------------
# Heuristic ticker extraction — whitelist + stoplist
# ---------------------------------------------------------------------------


def test_ticker_extraction_with_whitelist() -> None:
    text = "Chart of BTC and ETH; also references USA and AI"
    out = ce.extract_from_caption(text, ticker_whitelist={"BTC", "ETH"})
    assert sorted(out["tickers"]) == ["BTC", "ETH"]


def test_ticker_extraction_filters_stoplist() -> None:
    text = "GDP rising; AI infrastructure deals; USD strength"
    out = ce.extract_from_caption(text, ticker_whitelist=None)
    # Stoplist removes GDP, AI, USD even when no whitelist.
    assert out["tickers"] == []


def test_ticker_extraction_no_whitelist_keeps_unknown_ish() -> None:
    """Without whitelist, only stoplist gates → 'BABA' (not in stoplist) passes."""
    text = "BABA reported earnings"
    out = ce.extract_from_caption(text, ticker_whitelist=None)
    assert "BABA" in out["tickers"]


def test_ticker_extraction_dedupes() -> None:
    text = "BTC again, BTC again, BTC again"
    out = ce.extract_from_caption(text, ticker_whitelist={"BTC"})
    assert out["tickers"] == ["BTC"]


def test_ticker_extraction_preserves_order() -> None:
    text = "First META, then GOOGL, then AAPL"
    out = ce.extract_from_caption(
        text, ticker_whitelist={"META", "GOOGL", "AAPL"}
    )
    assert out["tickers"] == ["META", "GOOGL", "AAPL"]


def test_extract_returns_parse_failed_true() -> None:
    """Heuristic path always returns parse_failed=True so caller knows the
    extraction was salvaged, not LLM-confirmed."""
    out = ce.extract_from_caption("Candlestick chart of BTC on 1D")
    assert out["parse_failed"] is True


def test_extract_empty_caption() -> None:
    out = ce.extract_from_caption("")
    assert out["chart_type"] is None
    assert out["timeframe"] is None
    assert out["tickers"] == []


# ---------------------------------------------------------------------------
# Whitelist loader — async, mocked DB + The Street
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_ticker_whitelist_combines_sources() -> None:
    """Mocked watchlist + boards + The Street → unioned uppercase set."""
    with patch("app.watchlist.service.list_symbols", new=AsyncMock(return_value=["nvda", "META"])), \
         patch("app.boards.service.list_boards", new=AsyncMock(return_value=[
            {"id": "b1", "name": "Tech"},
         ])), \
         patch("app.boards.service.get_board", new=AsyncMock(return_value={
            "id": "b1", "tickers": [{"ticker": "googl"}, {"ticker": "AAPL"}],
         })), \
         patch("tools.the_street.query.list_snapshots", return_value=[]):
        result = await ce.load_ticker_whitelist()
    assert {"NVDA", "META", "GOOGL", "AAPL"}.issubset(result)


@pytest.mark.asyncio
async def test_load_ticker_whitelist_handles_db_failure() -> None:
    """Any source failing → load continues with the others; never raises."""
    with patch("app.watchlist.service.list_symbols", side_effect=RuntimeError("db down")), \
         patch("app.boards.service.list_boards", new=AsyncMock(return_value=[])), \
         patch("tools.the_street.query.list_snapshots", return_value=[]):
        result = await ce.load_ticker_whitelist()
    # Returned set still type-correct (empty here); no crash.
    assert isinstance(result, set)


def test_load_ticker_whitelist_sync_wraps_async() -> None:
    """Sync wrapper runs the async loader. Returns empty on internal failures."""
    with patch("app.watchlist.service.list_symbols", side_effect=RuntimeError("any")), \
         patch("app.boards.service.list_boards", side_effect=RuntimeError("any")), \
         patch("tools.the_street.query.list_snapshots", return_value=[]):
        result = ce.load_ticker_whitelist_sync()
    assert isinstance(result, set)
