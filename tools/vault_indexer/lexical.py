"""Lexical (FTS5) signal — Phase E Commit 4.

Adds a SQLite FTS5 virtual table indexing chunk text + node title + section,
used as the second leg of a hybrid retrieval pipeline. Together with the
vector KNN signal, RRF-merged in :mod:`search`, this catches queries with
strong lexical anchors that pure-vector ranking under-weights (proper
nouns, exact phrasing, rare terminology).

Why FTS5 (not LIKE):
  - BM25 scoring out of the box; no manual relevance heuristic
  - Porter-stemmed tokenisation handles plurals + verb forms
  - Sub-millisecond on 100k-chunk corpora
  - Available in the stock sqlite SQLite ships with macOS Python 3.12

Lifecycle:
  - :func:`init_fts` is called by ``cache.init`` to create the virtual table
    if it doesn't exist. Idempotent.
  - :func:`rebuild` drops + repopulates the table from current vault_chunk
    rows. Called on the indexer's startup migration path AND on every
    POST /reload so the lexical index stays in sync with vault content.
    Cost: a few hundred milliseconds per thousand chunks — acceptable for
    operator-tempo /reload cadence (manual / nightly cron, not request hot
    path).

No per-chunk triggers: the corpus is small enough (≤ tens of thousands of
chunks) that a full FTS rebuild on /reload is cheaper to reason about than
trigger maintenance, and the cache file is rebuildable from the vault
anyway.
"""
from __future__ import annotations

import logging
from typing import Optional

import apsw

log = logging.getLogger("vault-indexer.lexical")


_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS vault_chunk_fts USING fts5(
    path UNINDEXED,
    ord UNINDEXED,
    content,
    tokenize = 'porter unicode61 remove_diacritics 1'
);
"""


def init_fts(con: apsw.Connection) -> None:
    """Create the FTS5 virtual table if it doesn't exist. Idempotent."""
    cur = con.cursor()
    cur.execute(_FTS_DDL)


def sync_chunks_for_path(cur: apsw.Cursor, path: str) -> int:
    """Re-sync ``vault_chunk_fts`` rows for a single ``path``.

    Called from :func:`cache.replace_chunks` after the chunk swap so FTS5
    stays in step with vault_chunk on every ingest — operator-added content
    is searchable via lexical immediately, not on next /reload sweep.

    Idempotent. Cost: one DELETE + N INSERT per call (N ≈ chunks per doc,
    typically 5-30). Sub-millisecond on live cache.

    Returns the count of FTS rows inserted.
    """
    # Drop any stale FTS rows for this path
    cur.execute("DELETE FROM vault_chunk_fts WHERE path = ?", (path,))
    # Re-read the new chunks + title. Materialise to a list because apsw
    # cursors can't be iterated while an INSERT is pending on the same cursor.
    rows = list(cur.execute(
        """
        SELECT c.ord, c.text, c.section, n.title
        FROM vault_chunk c
        JOIN vault_node n ON n.path = c.path
        WHERE c.path = ?
        """,
        (path,),
    ))
    inserted = 0
    for ord_, text, section, title in rows:
        doc = " ".join(s for s in (title or "", section or "", text or "") if s)
        cur.execute(
            "INSERT INTO vault_chunk_fts (path, ord, content) VALUES (?, ?, ?)",
            (path, ord_, doc),
        )
        inserted += 1
    return inserted


def delete_path(cur: apsw.Cursor, path: str) -> int:
    """Remove all FTS rows for ``path``. Called from :func:`cache.delete_node`.

    Returns the count of FTS rows deleted (best-effort; apsw doesn't expose
    affected-rows count, so we count via SELECT first when accuracy matters
    — here we just return 1 to signal "executed").
    """
    cur.execute("DELETE FROM vault_chunk_fts WHERE path = ?", (path,))
    return 1


def rebuild(con: apsw.Connection) -> int:
    """Drop + repopulate ``vault_chunk_fts`` from current ``vault_chunk`` +
    ``vault_node`` rows. Returns the count of rows inserted.

    The lexical document is the chunk text PLUS the parent node's title
    and the chunk's section — three signals concatenated. This lets a
    query that hits the section heading (a common case for operator-typed
    queries that name a concept) rank the chunk highly even when the
    body text uses different vocabulary.

    Implementation note: apsw cursors don't support interleaved iteration
    (a SELECT in-progress gets reset when the same cursor runs an INSERT),
    so we materialise the SELECT into a list first.
    """
    cur = con.cursor()
    cur.execute("DELETE FROM vault_chunk_fts")
    rows = list(cur.execute(
        """
        SELECT c.path, c.ord, c.text, c.section, n.title
        FROM vault_chunk c
        JOIN vault_node n ON n.path = c.path
        """
    ))
    inserted = 0
    for path, ord_, text, section, title in rows:
        # Concatenate the three textual fields. Empty/None coerced to "" to
        # keep FTS5 happy. Title + section first so they get tokenisation
        # weight equivalent to the body text (FTS5 has no column weighting
        # without manual bm25 args; co-locating tokens is the cheap path).
        doc = " ".join(s for s in (title or "", section or "", text or "") if s)
        cur.execute(
            "INSERT INTO vault_chunk_fts (path, ord, content) VALUES (?, ?, ?)",
            (path, ord_, doc),
        )
        inserted += 1
    log.info("FTS rebuild: %d chunks indexed", inserted)
    return inserted


def search(
    con: apsw.Connection,
    query: str,
    *,
    k: int = 20,
    filter_sql: Optional[str] = None,
    filter_params: Optional[list] = None,
) -> list[dict]:
    """Run an FTS5 MATCH query over ``vault_chunk_fts``. Returns ranked rows.

    The query is wrapped in :func:`_sanitize_query` so operator-typed prose
    (with quotes, punctuation, capital letters) is converted to an FTS5
    boolean query without raising syntax errors.

    ``filter_sql`` + ``filter_params`` (Phase E refinement, 2026-05-16): when
    provided, JOIN vault_chunk + vault_node onto the FTS results and apply
    the same anchor-derived WHERE clause that ``query_parse.build_filter_sql``
    produces for the vector leg. Aliases in the clause MUST match what
    build_filter_sql emits — ``c.path`` for chunk path filters, ``n.kind``
    for kind, ``n.published_at`` for since. Without this, lexical hits bypass
    the operator's structural intent (e.g. AAPL ticker query surfaces
    non-Filings content the vector leg correctly excluded).

    Returns: list of ``{path, ord, rank, lexical_score}`` dicts, ordered by
    ascending rank (FTS5 rank is negative bm25; lower = more relevant).
    Empty list when the query has no usable tokens or matches nothing.
    """
    safe = _sanitize_query(query)
    if not safe:
        return []
    cur = con.cursor()
    try:
        if filter_sql:
            # JOIN chunk + node so build_filter_sql's `c.path` / `n.kind` /
            # `n.published_at` references resolve. The MATCH operator must
            # reference `vault_chunk_fts` by its full name (FTS5 doesn't
            # accept the table alias on the MATCH side).
            sql = (
                "SELECT vault_chunk_fts.path, vault_chunk_fts.ord, vault_chunk_fts.rank "
                "FROM vault_chunk_fts "
                "JOIN vault_chunk c ON c.path = vault_chunk_fts.path "
                "  AND c.ord = vault_chunk_fts.ord "
                "JOIN vault_node n ON n.path = c.path "
                "WHERE vault_chunk_fts MATCH ? "
                f"  AND {filter_sql} "
                "ORDER BY vault_chunk_fts.rank LIMIT ?"
            )
            params = (safe, *(filter_params or []), int(k))
        else:
            sql = (
                "SELECT path, ord, rank FROM vault_chunk_fts "
                "WHERE vault_chunk_fts MATCH ? ORDER BY rank LIMIT ?"
            )
            params = (safe, int(k))
        rows = list(cur.execute(sql, params))
    except apsw.SQLError:                            # noqa: BLE001
        # Malformed query (operator typed something the sanitiser missed).
        # Return empty rather than crashing; vector signal alone still works.
        return []
    out: list[dict] = []
    for path, ord_, rank in rows:
        # FTS5 rank is a negative-going bm25 (more relevant = more negative).
        # Convert to positive 0..1 for downstream use; reciprocal mapping
        # avoids needing a max-rank pass.
        out.append({
            "path": path,
            "ord": int(ord_),
            "rank": float(rank),
            "lexical_score": 1.0 / (1.0 + abs(float(rank))),
        })
    return out


def token_count(query: str) -> int:
    """Return the number of usable FTS tokens in ``query``.

    Used by callers to gate lexical search on minimum-query-length. Cheaper
    than running :func:`_sanitize_query` and re-splitting the OR-joined
    output (which would double-count the OR keyword).
    """
    if not query:
        return 0
    cleaned = []
    for ch in query.lower():
        if ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return sum(1 for t in "".join(cleaned).split() if len(t) >= 2)


# ---------------------------------------------------------------------------
# Query sanitisation
# ---------------------------------------------------------------------------

def _sanitize_query(query: str) -> str:
    """Turn an operator-typed query into a safe FTS5 MATCH expression.

    Strategy:
      - Strip punctuation that would break FTS5 syntax (`"`, `(`, `)`, `*`,
        `:`, `^`, `~`, etc.).
      - Lowercase and split on whitespace.
      - Drop tokens shorter than 2 chars (FTS5 ignores them anyway; explicit
        drop avoids tripping the parser on stray apostrophes).
      - Join with explicit ``OR`` so partial-match chunks contribute to the
        ranking (BM25 still favors chunks containing MORE of the rare query
        tokens — RRF + vector overlay handle the precision side).
      - Empty string when no usable tokens remain.

    Why OR (not AND): operator queries are typically 3-6 tokens describing a
    concept (e.g. "watchlist hygiene thesis discipline"); few individual
    chunks contain ALL tokens, so AND-mode produces zero hits on most useful
    queries. OR + BM25 ranking + RRF merge with the vector signal is the
    high-recall + high-precision combo.
    """
    if not query:
        return ""
    # Convert anything non-alphanumeric to a space. Don't preserve `-` or `_`
    # — `-` is the FTS5 NOT operator and `forward-looking` would parse as
    # `forward NOT looking`; splitting at the hyphen lets the unicode61
    # tokeniser treat each half as an independent token (which is what the
    # FTS index itself stored).
    cleaned = []
    for ch in query.lower():
        if ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    tokens = [t for t in "".join(cleaned).split() if len(t) >= 2]
    if not tokens:
        return ""
    return " OR ".join(tokens)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def rrf_merge(
    vector_results: list[dict],
    lexical_results: list[dict],
    *,
    vector_weight: float = 1.0,
    lexical_weight: float = 0.5,
    rrf_k: int = 60,
) -> list[dict]:
    """Merge two ranked lists via Reciprocal Rank Fusion.

    For each item appearing in either list, compute:

        score = (vector_weight  / (rrf_k + rank_v))
              + (lexical_weight / (rrf_k + rank_l))

    where missing-rank contributes 0. ``rrf_k=60`` is the standard
    smoothing constant from the original RRF paper (Cormack et al. 2009).

    Items are identified by ``(path, ord)`` so multiple chunks per doc
    rank independently. The merged list preserves each item's original
    dict from the *vector* side when available, else the lexical side,
    plus the fused ``rrf_score`` field for downstream sorting.

    ``vector_weight=1.0, lexical_weight=0.5`` is a sane finance default
    where vector ranking has been working well; biasing higher toward
    vector (`lexical_weight≈0.05`) reduces lexical's influence on
    fitness/nutrition where the corpus is small and lexical noise
    outweighs signal.
    """
    by_key: dict[tuple[str, int], dict] = {}
    # Vector contributions
    for rank_v, item in enumerate(vector_results):
        key = (item.get("path"), int(item.get("ord", 0)))
        contrib = vector_weight / (rrf_k + rank_v)
        merged = dict(item)
        merged["rrf_score"] = contrib
        merged["rank_vector"] = rank_v
        by_key[key] = merged
    # Lexical contributions
    for rank_l, item in enumerate(lexical_results):
        key = (item.get("path"), int(item.get("ord", 0)))
        contrib = lexical_weight / (rrf_k + rank_l)
        if key in by_key:
            by_key[key]["rrf_score"] += contrib
            by_key[key]["rank_lexical"] = rank_l
            by_key[key]["lexical_score"] = item.get("lexical_score")
        else:
            merged = dict(item)
            merged["rrf_score"] = contrib
            merged["rank_lexical"] = rank_l
            by_key[key] = merged
    # Sort by fused score desc
    out = list(by_key.values())
    out.sort(key=lambda r: r.get("rrf_score", 0.0), reverse=True)
    return out
