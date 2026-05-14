"""Heuristic chart-reference extractor — Stage 2 of L3 structured chart refs.

Two responsibilities:

1. **Heuristic salvage** — when ``vlm_adapter.caption_frame_structured``
   returns ``parse_failed=True`` (YAML output malformed), regex the
   free-form caption to recover what we can: chart_type, timeframe,
   tickers (whitelist-filtered). Never raises.

2. **Whitelist resolution** — load the dynamic ticker universe
   (roster ∪ all boards ∪ The Street tier-1/2 from last 4 snapshots).
   Used both as a stoplist on Stage 2 regex AND as the gate for
   ``app.ticker_review.enqueue_or_bump`` (unknown tickers from Stage 1
   that aren't whitelisted → review queue).

Pure-Python, no MLX. Deterministic. Tested via mocked watchlist + Street
fixtures so CI is fast and offline.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Heuristic regex — Stage 2 fallback when VLM YAML output unusable.
# -----------------------------------------------------------------------------


_CHART_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcandlesticks?\b|\bcandle chart\b|\bcandle stick\b", re.IGNORECASE), "candlestick"),
    (re.compile(r"\bline (?:graph|chart)\b|\bline-graph\b", re.IGNORECASE), "line"),
    (re.compile(r"\bbar (?:graph|chart)\b", re.IGNORECASE), "bar"),
    (re.compile(r"\barea (?:graph|chart)\b", re.IGNORECASE), "area"),
    (re.compile(r"\bgauge\b", re.IGNORECASE), "gauge"),
    (re.compile(r"\bscatter (?:plot|chart)\b", re.IGNORECASE), "scatter"),
    (re.compile(r"\bhistogram\b", re.IGNORECASE), "histogram"),
    (re.compile(r"\bpie chart\b", re.IGNORECASE), "pie"),
]

# Order matters — longer literal matches first so '1mo' wins over '1m'.
_TIMEFRAME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b1\s*mo\b|\b1[-\s]?month\b|\bmonthly\b", re.IGNORECASE), "1mo"),
    (re.compile(r"\b3\s*mo\b|\b3[-\s]?months?\b|\bquarterly\b", re.IGNORECASE), "3mo"),
    (re.compile(r"\b6\s*mo\b|\b6[-\s]?months?\b", re.IGNORECASE), "6mo"),
    (re.compile(r"\b1\s*y\b|\b1[-\s]?year\b|\byearly\b|\bannual\b", re.IGNORECASE), "1y"),
    (re.compile(r"\b2\s*y\b|\b2[-\s]?years?\b", re.IGNORECASE), "2y"),
    (re.compile(r"\b5\s*y\b|\b5[-\s]?years?\b", re.IGNORECASE), "5y"),
    (re.compile(r"\b10\s*y\b|\b10[-\s]?years?\b", re.IGNORECASE), "10y"),
    (re.compile(r"\b1\s*w\b|\b1[-\s]?week\b|\bweekly\b", re.IGNORECASE), "1w"),
    (re.compile(r"\b2\s*w\b|\b2[-\s]?weeks?\b", re.IGNORECASE), "2w"),
    (re.compile(r"\b1\s*d\b|\b1[-\s]?day\b|\bdaily\b", re.IGNORECASE), "1d"),
    (re.compile(r"\b2\s*d\b|\b2[-\s]?days?\b", re.IGNORECASE), "2d"),
    (re.compile(r"\b3\s*d\b|\b3[-\s]?days?\b", re.IGNORECASE), "3d"),
    (re.compile(r"\b12\s*h\b|\b12[-\s]?hours?\b", re.IGNORECASE), "12h"),
    (re.compile(r"\b8\s*h\b|\b8[-\s]?hours?\b", re.IGNORECASE), "8h"),
    (re.compile(r"\b6\s*h\b|\b6[-\s]?hours?\b", re.IGNORECASE), "6h"),
    (re.compile(r"\b4\s*h\b|\b4[-\s]?hours?\b|\bfour[-\s]?hour\b", re.IGNORECASE), "4h"),
    (re.compile(r"\b2\s*h\b|\b2[-\s]?hours?\b", re.IGNORECASE), "2h"),
    (re.compile(r"\b1\s*h\b|\b1[-\s]?hour\b|\bhourly\b", re.IGNORECASE), "1h"),
    (re.compile(r"\b30\s*m\b|\b30[-\s]?minutes?\b", re.IGNORECASE), "30m"),
    (re.compile(r"\b15\s*m\b|\b15[-\s]?minutes?\b", re.IGNORECASE), "15m"),
    (re.compile(r"\b5\s*m\b|\b5[-\s]?minutes?\b", re.IGNORECASE), "5m"),
    (re.compile(r"\b1\s*m\b|\b1[-\s]?minute\b", re.IGNORECASE), "1m"),
]

# Find candidate ticker-shaped tokens (uppercase 1-5 letters), then
# filter against the dynamic whitelist. Without the whitelist, every
# acronym becomes a ticker — see `_DEFAULT_STOPLIST` for the always-off
# set even when whitelist is empty.
_TICKER_TOKEN_RE = re.compile(r"\b[A-Z]{1,5}\b")

# Hard stoplist — even with `whitelist=None`, these never count as tickers.
# Covers common acronyms surfaced by Qwen2-VL on financial videos.
_DEFAULT_STOPLIST = {
    # Generic
    "A", "AI", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "PM", "SO", "TO",
    "UP", "US", "WE",
    # Macro / news acronyms
    "CEO", "CFO", "CTO", "ETF", "FED", "GDP", "USA", "USD", "EUR", "GBP",
    "JPY", "VAT", "TAX", "IPO", "LBO", "PE", "VC", "AI", "ML", "API",
    "SEC", "FBI", "CIA", "NYC", "LA", "UK", "EU", "UN", "WTO", "IMF",
    "CNBC", "CNN", "NPR", "WSJ", "FT", "BBC", "OK", "TV", "USB",
    "Q1", "Q2", "Q3", "Q4",
    # Tech-buzz that often shows up on AI-themed slides
    "LLM", "RAG", "GPT", "BERT", "AWS", "GCP", "AZURE", "SAAS", "PAAS",
}


def extract_from_caption(
    caption: str,
    *,
    ticker_whitelist: Optional[Iterable[str]] = None,
    stoplist: Optional[set[str]] = None,
) -> dict:
    """Heuristic regex over the free-form caption. Salvage best-effort.

    Args:
        caption: prose returned by Qwen2-VL when structured YAML failed.
        ticker_whitelist: roster ∪ boards ∪ The Street. When None, only
            the stoplist gates ticker emission (noisier).
        stoplist: override the default stoplist. None → use defaults.

    Returns same shape as ``vlm_adapter.caption_frame_structured`` so
    callers can mix structured and heuristic results transparently:

      {chart_type, timeframe, tickers, topics, caption, parse_failed}

    ``topics`` is always [] from the heuristic — they're hard to extract
    without LLM. Topics get filled only via Stage 1 (VLM structured).
    """
    if not caption or not isinstance(caption, str):
        return _empty_extract()

    text = caption

    chart_type = _match_first(_CHART_TYPE_PATTERNS, text)
    timeframe = _match_first(_TIMEFRAME_PATTERNS, text)

    sl = stoplist if stoplist is not None else _DEFAULT_STOPLIST
    wl_upper = {t.upper() for t in (ticker_whitelist or [])}
    tickers = _extract_tickers(text, whitelist=wl_upper, stoplist=sl)

    return {
        "chart_type": chart_type,
        "timeframe": timeframe,
        "tickers": tickers,
        "topics": [],
        "caption": caption.strip(),
        "parse_failed": True,  # heuristic salvage path; signals provenance
    }


def _empty_extract() -> dict:
    return {
        "chart_type": None,
        "timeframe": None,
        "tickers": [],
        "topics": [],
        "caption": "",
        "parse_failed": True,
    }


def _match_first(patterns: list[tuple[re.Pattern, str]], text: str) -> Optional[str]:
    for pat, label in patterns:
        if pat.search(text):
            return label
    return None


def _extract_tickers(
    text: str, *, whitelist: set[str], stoplist: set[str]
) -> list[str]:
    """Return uppercase tokens that pass:
      - regex shape (1-5 ASCII letters)
      - NOT in stoplist
      - IF whitelist provided: must be in whitelist
    Preserves first-seen order; dedupes.
    """
    out: list[str] = []
    seen: set[str] = set()
    for tok in _TICKER_TOKEN_RE.findall(text):
        if tok in stoplist:
            continue
        if whitelist and tok not in whitelist:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


# -----------------------------------------------------------------------------
# Whitelist loaders — dynamic; refreshed once per channel-poll tick.
# -----------------------------------------------------------------------------


async def load_ticker_whitelist() -> set[str]:
    """Roster ∪ all boards ∪ The Street tier-1/2 (last 4 snapshots).

    Async because boards + watchlist live in the laptop DB. The Street
    is a vault-scoped CLI helper (sync). Combined result is uppercase
    strings, deduped.

    Never raises. Returns an empty set on any failure so downstream
    behaviour is "stricter" — false negatives are preferred over
    crash-during-ingest.
    """
    universe: set[str] = set()

    # Watchlist (roster).
    try:
        from app.watchlist import service as _wl_svc

        for sym in await _wl_svc.list_symbols():
            if sym:
                universe.add(sym.upper())
    except Exception as e:  # noqa: BLE001
        logger.warning("chart_extractor: watchlist load failed: %s", e)

    # Boards — list_boards() returns dicts; each needs get_board() for tickers.
    try:
        from app.boards import service as _b_svc

        boards = await _b_svc.list_boards()
        for b in boards:
            board_full = await _b_svc.get_board(b["id"])
            if not board_full:
                continue
            for item in board_full.get("tickers", []):
                t = item.get("ticker")
                if t:
                    universe.add(t.upper())
    except Exception as e:  # noqa: BLE001
        logger.warning("chart_extractor: boards load failed: %s", e)

    # The Street — sync CLI helpers, run via asyncio.to_thread to keep
    # the async path non-blocking.
    try:
        import asyncio
        from tools.the_street import query as _street

        def _street_tickers() -> set[str]:
            out: set[str] = set()
            snaps = _street.list_snapshots()[-4:]
            for snap in snaps:
                for tier in (1, 2):
                    try:
                        for row in _street.list_tier(tier, snap):
                            t = row.get("ticker", "") or row.get("symbol", "")
                            if t:
                                out.add(str(t).upper())
                    except Exception:
                        pass
            return out

        universe |= await asyncio.to_thread(_street_tickers)
    except Exception as e:  # noqa: BLE001
        logger.warning("chart_extractor: The Street load failed: %s", e)

    return universe


def load_ticker_whitelist_sync() -> set[str]:
    """Sync convenience wrapper for the channel-poll tick (synchronous).

    Wraps the async loader by running a fresh event loop. Cheap since
    the underlying queries are short. Returns empty set on any failure.
    """
    import asyncio

    try:
        return asyncio.run(load_ticker_whitelist())
    except Exception as e:  # noqa: BLE001
        logger.warning("chart_extractor: whitelist load (sync) failed: %s", e)
        return set()
