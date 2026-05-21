"""Shared constants for the rx layer — single source of truth for the
ticker regex + denylist used by:

  - ``app.rx.service.links_for_rec`` (cross-references hypothesis + trade
    links from rec text)
  - ``app.rx.tv_context_signal.extract_tickers`` (operator-attention
    axis: which tickers does this rec mention?)
  - ``frontend/src/pages/RxFinanceDetail.tsx`` (UI prefill for the
    "Log trade from this rec" CTA — mirrors this set verbatim in
    `TICKER_NOISE_DENYLIST`)

Extracted 2026-05-20 so the three call sites can't drift apart silently.
Previous shape had `service.py` own the denylist and `tv_context_signal.py`
import it via ``from app.rx.service import _TICKER_NOISE_DENYLIST`` —
fragile module-load coupling that breaks the moment service.py imports
are restructured.

NOTE: the vault-indexer's chart_extractor has its OWN denylist; that one
lives in `tools/vault_indexer/ingest/chart_extractor.py` because the
indexer must run without depending on the FastAPI app's package tree.
Keep them in sync manually when adding new noise tokens.
"""
from __future__ import annotations

import re


# Compiled regex over ALL-CAPS 2-5 letter tokens. Anchored at word
# boundaries. Captures every potential ticker; the denylist below
# rejects the obvious non-tickers (USA, GDP, BUY, etc.). Single
# uppercase letters (T, F, X) are NOT matched — too noisy for prose;
# the indexer's chart_extractor has the same constraint.
TICKER_TOKEN_RE = re.compile(r"\b[A-Z]{2,5}\b")


# Common ALL-CAPS tokens that match the regex but never identify a real
# ticker in a finance rec body. Operator can grow this if a new noise
# token starts polluting the cross-references panel or the attention
# axis. Tickers that ALSO appear as words (TWLO etc. are unique;
# HOLD/BUY/CASH are not).
TICKER_NOISE_DENYLIST: frozenset[str] = frozenset({
    "AI", "API", "BUY", "CEO", "CFO", "CPI", "CPU", "DCF", "EBIT",
    "EBITDA", "EOD", "ETF", "FAQ", "FED", "FOMC", "GDP", "GPU", "HOLD",
    "IPO", "IRR", "LBO", "MA", "OPEN", "OTC", "PE", "PMI", "ROI", "RSI",
    "SELL", "SP", "SPX", "SP500", "SPY", "TBD", "TLDR", "UK", "US", "USA",
    "VIX", "WSJ", "YOY", "YTD",
})


def extract_tickers(*texts: str | None) -> list[str]:
    """Extract uppercase 2-5 letter ticker candidates from concatenated
    free-text inputs. Applies the denylist. Returns deduped first-seen
    order — same shape both callers want.

    Empty / None inputs are tolerated.
    """
    haystack = " ".join(t for t in texts if t)
    if not haystack:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for tok in TICKER_TOKEN_RE.findall(haystack):
        if tok in TICKER_NOISE_DENYLIST or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out
