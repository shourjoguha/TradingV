"""Query parser — Phase E Commit 3.

Extracts hard anchors (tickers, doc kinds, time phrases) from a free-text
query so :mod:`search` can narrow the KNN candidate pool before vector
similarity scoring. Three signals:

  - **Tickers**: short uppercase tokens that match a lexicon derived from
    vault paths (``Filings/<TICKER>/...`` and ``Research/<date>-<ticker>-...``).
    No backend dependency — lexicon built from the cache itself, refreshed
    lazily on first call per process.
  - **Kinds**: closed-set keywords (``book``, ``video``, ``earnings``,
    ``newsletter``, ``transcript`` etc.) with alias expansion to the
    ``vault_node.kind`` taxonomy.
  - **Time phrases**: ``today``, ``last week``, ``recent``, ``<MMM YYYY>``,
    ``<YYYY>`` resolved to an inclusive ``since`` date.

The parser is pure: no I/O, no logging. Lexicon loading happens once per
process via :func:`load_ticker_lexicon`.

Design notes:

  - Token detection is **conservative**: only emit a ticker when the token
    matches both the uppercase shape AND the lexicon. Avoids false positives
    on tokens like ``USA`` or ``GDP`` that look ticker-shaped.
  - Case-insensitive for kinds and time phrases; case-sensitive for tickers
    (operator types tickers uppercase by convention).
  - Returns ``raw_terms`` = original tokens MINUS any consumed by extraction.
    Caller can use these for FTS5/lexical search later (Commit 4).
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Kind synonyms — map operator phrasing to vault_node.kind values
# ---------------------------------------------------------------------------

_KIND_ALIASES: dict[str, list[str]] = {
    "book":               ["book", "book_chapter"],
    "books":              ["book", "book_chapter"],
    "chapter":            ["book_chapter"],
    "newsletter":         ["newsletter"],
    "newsletters":        ["newsletter"],
    "video":              ["video"],
    "videos":             ["video"],
    "transcript":         ["video"],
    "transcripts":        ["video"],
    "note":               ["note"],
    "notes":              ["note"],
    "topic":              ["topic"],
    "topics":             ["topic"],
    "filing":             ["filing"],
    "filings":            ["filing"],
    "earnings":           ["filing"],
    "earning":            ["filing"],
    "10-q":               ["filing"],
    "10-k":               ["filing"],
    "8-k":                ["filing"],
    "research":           ["research_answer"],
    "snapshot":           ["smart_money_snapshot"],
    "snapshots":          ["smart_money_snapshot"],
    "tier-1":             ["smart_money_snapshot"],
    "tier-2":             ["smart_money_snapshot"],
    "screenshot":         ["tradingview-screenshot"],
    "screenshots":        ["tradingview-screenshot"],
}


# ---------------------------------------------------------------------------
# Time phrases — words/phrases → "days back from today"
# ---------------------------------------------------------------------------

# Static day-offset table for common relative phrases. Ordered longest first
# so the multi-word matcher prefers "last week" over "last".
_TIME_PHRASES: list[tuple[str, int]] = [
    ("this quarter", 90),
    ("last quarter", 180),
    ("this month",   30),
    ("last month",   60),
    ("this week",     7),
    ("last week",    14),
    ("recent",       30),
    ("recently",     30),
    ("lately",       30),
    ("today",         1),
    ("yesterday",     2),
    ("this year",   365),
    ("last year",   730),
]

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_MONTH_YEAR_RE = re.compile(
    r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+"
    r"(\d{4})\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


# ---------------------------------------------------------------------------
# ParsedQuery
# ---------------------------------------------------------------------------

@dataclass
class ParsedQuery:
    """Result of :func:`parse`. All fields may be empty.

    ``tickers``: list of detected ticker symbols (uppercase).
    ``kinds``: list of ``vault_node.kind`` values to filter to (after
        alias expansion).
    ``since``: inclusive lower bound on ``published_at``. ``None`` when no
        time phrase detected.
    ``raw_terms``: original tokens with extracted anchors removed. Useful
        for downstream lexical search (Commit 4).
    """

    tickers: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    since: Optional[datetime.date] = None
    raw_terms: list[str] = field(default_factory=list)

    def has_anchors(self) -> bool:
        """True if any structured signal was detected."""
        return bool(self.tickers or self.kinds or self.since)


# ---------------------------------------------------------------------------
# Lexicon loading
# ---------------------------------------------------------------------------

def load_ticker_lexicon(con) -> set[str]:
    """Build the ticker lexicon from current vault content.

    Sources:
      - ``Filings/<TICKER>/...`` — second path segment when first = ``Filings``.
      - ``Research/<date>-<ticker>-...`` — uppercase ticker token in the
        Research filename.

    Returns a fresh set; caller caches as needed. Cheap (single SELECT).
    """
    out: set[str] = set()
    rows = con.execute(
        "SELECT path FROM vault_node "
        "WHERE path LIKE 'Filings/%' OR path LIKE 'Research/%'"
    )
    research_re = re.compile(r"^Research/\d{4}-\d{2}-\d{2}-([A-Z]{1,5})-", re.IGNORECASE)
    for (path,) in rows:
        if path.startswith("Filings/"):
            segs = path.split("/", 2)
            if len(segs) >= 2 and segs[1]:
                tok = segs[1]
                if _TICKER_RE.fullmatch(tok):
                    out.add(tok)
        else:
            m = research_re.match(path)
            if m:
                out.add(m.group(1).upper())
    return out


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse(
    query: str,
    *,
    ticker_lexicon: Optional[set[str]] = None,
    today: Optional[datetime.date] = None,
) -> ParsedQuery:
    """Extract anchors from ``query``. Pure function (no I/O).

    ``ticker_lexicon`` filters which uppercase tokens count as tickers
    (avoids false positives on ``USA``, ``GDP``, etc.). When ``None``,
    no ticker detection runs.

    ``today`` overridable for testability; defaults to today's date in
    UTC.
    """
    if today is None:
        today = datetime.datetime.now(tz=datetime.timezone.utc).date()

    text = query.strip()
    low = text.lower()
    tickers: list[str] = []
    kinds: list[str] = []
    since: Optional[datetime.date] = None
    consumed_spans: list[tuple[int, int]] = []   # char ranges removed from raw_terms

    # 1. Tickers (uppercase, in lexicon)
    if ticker_lexicon:
        for m in _TICKER_RE.finditer(text):
            tok = m.group(1)
            if tok in ticker_lexicon and tok not in tickers:
                tickers.append(tok)
                consumed_spans.append(m.span())

    # 2. Kind keywords (case-insensitive, exact-token match)
    # Need word-boundary match against lowercased text.
    for kw, kinds_for_kw in _KIND_ALIASES.items():
        pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
        for m in pattern.finditer(low):
            for k in kinds_for_kw:
                if k not in kinds:
                    kinds.append(k)
            consumed_spans.append(m.span())

    # 3. Time phrases (multi-word phrases first)
    for phrase, days_back in _TIME_PHRASES:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        m = pattern.search(low)
        if m:
            candidate = today - datetime.timedelta(days=days_back)
            since = candidate if since is None else min(since, candidate)
            consumed_spans.append(m.span())
            break  # one phrase wins; first match by table order

    # 4. Month + year ("May 2026")
    m = _MONTH_YEAR_RE.search(text)
    if m:
        month = _MONTHS[m.group(1).lower()]
        year = int(m.group(2))
        # since = first of that month, captures the month's content
        candidate = datetime.date(year, month, 1)
        since = candidate if since is None else min(since, candidate)
        consumed_spans.append(m.span())

    # 5. Year alone ("2026") — only if no since already set
    if since is None:
        m = _YEAR_RE.search(text)
        if m:
            year = int(m.group(1))
            since = datetime.date(year, 1, 1)
            consumed_spans.append(m.span())

    raw_terms = _strip_spans(text, consumed_spans).split()

    return ParsedQuery(
        tickers=tickers, kinds=kinds, since=since, raw_terms=raw_terms,
    )


def _strip_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Remove char ranges from ``text`` (overlapping spans tolerated)."""
    if not spans:
        return text
    # Merge overlapping spans
    spans = sorted(spans)
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    # Build output by skipping merged spans
    out: list[str] = []
    cursor = 0
    for start, end in merged:
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return " ".join(s for s in out if s)


# ---------------------------------------------------------------------------
# SQL helper — build a WHERE clause from a parsed query
# ---------------------------------------------------------------------------

def build_filter_sql(parsed: ParsedQuery) -> tuple[str, list]:
    """Return ``(where_fragment, params)`` for a SELECT against ``vault_node``.

    Caller composes this onto its existing query. Returns empty string +
    empty params when no anchors → no filter.

    The fragment is **chunk-aware**: tickers match on ``vault_chunk.path``
    via LIKE patterns (Filings/<T>/% OR Research/...<t>...). Kinds match
    on ``vault_node.kind``. Since matches on ``vault_node.published_at``.

    Designed to be AND-ed onto the search query's chunk JOIN, so the caller
    must reference ``c.path`` and ``n.kind`` / ``n.published_at`` aliases
    when composing.
    """
    if not parsed.has_anchors():
        return "", []
    clauses: list[str] = []
    params: list = []

    if parsed.tickers:
        tick_clauses = []
        for t in parsed.tickers:
            tick_clauses.append("c.path LIKE ?")
            params.append(f"Filings/{t}/%")
            tick_clauses.append("c.path LIKE ?")
            params.append(f"Research/%-{t.lower()}-%")
            tick_clauses.append("c.path LIKE ?")
            params.append(f"Research/%-{t}-%")
        clauses.append("(" + " OR ".join(tick_clauses) + ")")

    if parsed.kinds:
        placeholders = ",".join(["?"] * len(parsed.kinds))
        clauses.append(f"n.kind IN ({placeholders})")
        params.extend(parsed.kinds)

    if parsed.since:
        clauses.append("(n.published_at IS NULL OR n.published_at >= ?)")
        params.append(parsed.since.isoformat())

    return " AND ".join(clauses), params
