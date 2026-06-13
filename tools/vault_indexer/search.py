"""Retrieval — embed query, KNN over sqlite-vec, apply decay weighting."""
from __future__ import annotations

import json
import struct
from typing import Optional

from . import cache as _cache
from . import decay as _decay
from . import embed as _embed
from . import hybrid as _hybrid
from . import lexical as _lexical
from . import query_parse as _qp
from . import retrieval_log as _rlog
from .config import CONFIG


def _maybe_log(
    con,
    *,
    query: str,
    mode: str,
    k: int,
    parsed,
    eligible_count: int,
    pre_cut: list[dict],
    surfaced: list[dict],
    enabled: bool,
) -> None:
    """Record this search to the retrieval log (best-effort).

    ``dropped`` = candidates that were fully scored but fell outside the
    top-k cut — the eligible-but-not-surfaced delta. In fast mode the reason
    is always rank; Phase 1 deep mode attaches richer per-candidate reasons
    upstream and they flow through here unchanged.
    """
    if not enabled:
        return
    try:
        surfaced_keys = {(s.get("path"), s.get("ord")) for s in surfaced}
        dropped = [
            {
                "path": c.get("path"),
                "ord": c.get("ord"),
                "score": c.get("score"),
                "reason": c.get("drop_reason", "below_top_k"),
            }
            for c in pre_cut
            if (c.get("path"), c.get("ord")) not in surfaced_keys
        ]
        anchors = None
        if parsed is not None and parsed.has_anchors():
            anchors = {
                "tickers": sorted(getattr(parsed, "tickers", set()) or []),
                "kinds": sorted(getattr(parsed, "kinds", set()) or []),
                "since": (
                    parsed.since.isoformat()
                    if getattr(parsed, "since", None)
                    else None
                ),
            }
        _rlog.record(
            con,
            query=query,
            mode=mode,
            domain=CONFIG.domain,
            k=k,
            anchors=anchors,
            eligible_count=max(eligible_count, len(pre_cut)),
            surfaced=surfaced,
            dropped=dropped,
        )
    except Exception:  # noqa: BLE001 — logging must never break search
        pass


# Process-cached ticker lexicon. Loaded lazily on first search call; refreshed
# on /reload via reset_ticker_lexicon(). Keeping it process-local (not module-
# level cache) lets tests reset between cases.
_TICKER_LEXICON: Optional[set[str]] = None


def reset_ticker_lexicon() -> None:
    """Force the ticker lexicon to be rebuilt on next search.

    Called from /reload so newly-ingested Filings/Research show up as
    recognisable tickers without a process restart.
    """
    global _TICKER_LEXICON
    _TICKER_LEXICON = None


def _ticker_lexicon(con) -> set[str]:
    global _TICKER_LEXICON
    if _TICKER_LEXICON is None:
        try:
            _TICKER_LEXICON = _qp.load_ticker_lexicon(con)
        except Exception:                            # noqa: BLE001
            _TICKER_LEXICON = set()
    return _TICKER_LEXICON


def search(
    con,
    query: str,
    *,
    k: int = 8,
    hypothesis_paths: Optional[list[str]] = None,
    hybrid: Optional[bool] = None,
    excerpts: bool = True,
    parse: bool = True,
    mode: str = "fast",
    log: bool = True,
) -> list[dict]:
    """Vector search with optional hybrid re-rank.

    ``hybrid`` parameter (None → CONFIG.graph_enabled) controls whether
    graph signals (citation_rank, centrality, recency boost) re-rank the
    results. The original ``score`` field is always preserved; ``hybrid_score``
    is added as a sibling key when re-ranking is effective.

    Below the ``min_edges_for_hybrid`` floor, hybrid is a no-op even when
    enabled — preserves baseline behavior on cold-start corpora.

    ``excerpts`` (default True) controls whether each result is annotated
    with the 2 sentences best matching the query (``excerpt_sentences``).
    Excerpt computation costs O(k * sentences_per_chunk) BGE forwards —
    ~1-3s per chunk on Apple Silicon — and is the dominant latency cost
    of ``/search``. UI consumers want this; MCP/bundle consumers already
    get the full chunk ``text`` and should pass ``excerpts=False``.

    ``parse`` (Phase E Commit 3): when True (default), the query string
    is run through :mod:`query_parse` to extract tickers / kinds / since
    anchors; matching anchors narrow the KNN candidate pool via SQL
    pre-filter before vector similarity ranking. When no anchors detect
    the pre-filter is a no-op (identical to ``parse=False``). Disabling
    is useful for ad-hoc literal vector queries from operators who don't
    want auto-anchor detection.
    """
    from . import excerpt as _excerpt

    qvec = _embed.encode_query(query)
    qblob = struct.pack(f"{len(qvec)}f", *qvec)

    # Phase E Commit 3: structural anchors first, before vector KNN.
    # The pre-filter narrows the candidate pool to chunks whose parent node
    # matches the parsed ticker / kind / since anchors. Empty parse →
    # no filter (legacy behaviour).
    parsed: Optional[_qp.ParsedQuery] = None
    if parse:
        parsed = _qp.parse(query, ticker_lexicon=_ticker_lexicon(con))

    # Pre-compute the anchor SQL once — used by BOTH vector and lexical legs
    # so they honour the same structural intent.
    anchor_sql: Optional[str] = None
    anchor_params: list = []
    if parsed and parsed.has_anchors():
        anchor_sql, anchor_params = _qp.build_filter_sql(parsed)

    # Ask vec0 for top (k * 4) by raw cosine; we'll re-rank with decay.
    # Over-fetch larger when filter present so post-filter we still have
    # ~k * 4 candidates after the WHERE-clause cull.
    base_raw_k = max(k * 4, 24)
    raw_k = base_raw_k * 4 if anchor_sql else base_raw_k

    if anchor_sql:
        filter_sql, filter_params = anchor_sql, anchor_params
        rows = list(con.execute(
            f"""
            SELECT v.chunk_id, v.distance, c.path, c.ord, c.text, c.section
            FROM vault_chunk_vec v
            JOIN vault_chunk c ON c.id = v.chunk_id
            JOIN vault_node n ON n.path = c.path
            WHERE v.embedding MATCH ? AND k = ? AND {filter_sql}
            ORDER BY v.distance
            """,
            (qblob, raw_k, *filter_params),
        ))
    else:
        rows = list(con.execute(
            """
            SELECT v.chunk_id, v.distance, c.path, c.ord, c.text, c.section
            FROM vault_chunk_vec v
            JOIN vault_chunk c ON c.id = v.chunk_id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (qblob, raw_k),
        ))
    # Raw eligible pool size (vector KNN over-fetch) — recorded by the
    # retrieval log as the denominator for "what could have surfaced".
    eligible_count = len(rows)

    if not rows:
        _maybe_log(
            con, query=query, mode=mode, k=k, parsed=parsed,
            eligible_count=0, pre_cut=[], surfaced=[], enabled=log,
        )
        return []

    # Distance is cosine distance ∈ [0, 2]; convert to similarity ∈ [-1, 1].
    # First pass: load nodes + compute similarity. Decay needs the full set to
    # compute within-group ranks, so we materialise rows first and apply decay
    # in a second pass.
    staged: list[tuple[dict, str, int, str, Optional[str], float]] = []
    seen_nodes: list[dict] = []
    for chunk_id, dist, path, ord_, text, section in rows:
        if hypothesis_paths is not None and path not in hypothesis_paths:
            continue
        node = _cache.get_node(con, path)
        if node is None:
            continue
        sim = 1.0 - float(dist)              # cosine distance → similarity
        staged.append((node, path, ord_, text, section, sim))
        seen_nodes.append(node)

    # Phase E Commit 2: within-group ranks (per `decay_group_key`) drive decay.
    # `assign_ranks` returns ``{path: rank}`` for grouped nodes; absent paths
    # are treated as ungrouped → no penalty.
    # Per-kind overrides let SEC filings group by ticker (Filings/<T>/) when
    # `author` is unset; their ladder + floor:0.0 caps the corpus at top-N
    # filings per ticker.
    ranks = (
        _decay.assign_ranks(
            seen_nodes,
            group_key=CONFIG.decay_group_key,
            kind_overrides=CONFIG.decay_kind_overrides,
        )
        if CONFIG.decay_mode == "ranked_grouped"
        else {}
    )

    out: list[dict] = []
    for node, path, ord_, text, section, sim in staged:
        node_rank = ranks.get(path)
        decay = _decay.weight_for(node, rank=node_rank)
        # Drop rows where the kind override has driven decay to 0 (e.g.
        # filings ranked past the keep-N-per-ticker cap). Equivalent to
        # filtering at the SQL layer, done here so other kinds keep flowing.
        if decay <= 0.0:
            continue
        score = sim * decay
        out.append({
            "path": path,
            "ord": ord_,
            "text": text,
            "section": section,
            "title": node.get("title"),
            "kind": node.get("kind"),
            "author": node.get("author"),
            "published_at": node.get("published_at"),
            "horizon_months": node.get("horizon_months"),
            "evergreen": node.get("evergreen"),
            "tags": node.get("tags"),
            "similarity": sim,
            "decay_weight": decay,
            "decay_rank": node_rank,
            "score": score,
        })
    out.sort(key=lambda r: r["score"], reverse=True)

    # Phase E Commit 4: lexical (FTS5) leg merged via Reciprocal Rank Fusion.
    # Skip when:
    #   - lexical disabled for this domain (config)
    #   - query has < min_tokens after sanitisation (too noisy single-word)
    #   - hypothesis_paths constraint active (lexical can't honour it)
    lexical_results: list[dict] = []
    if (
        CONFIG.lexical_enabled
        and hypothesis_paths is None
        and _lexical.token_count(query) >= CONFIG.lexical_min_tokens
    ):
        try:
            # Over-fetch lexical too so RRF has signal past the visible k.
            # Pass the SAME anchor filter the vector leg used — without this,
            # an "AAPL earnings" query's vector hits would be filings-only
            # but lexical would surface Research/aapl-wedge stubs + The Street
            # snapshots that share tokens, defeating the operator's intent.
            lexical_results = _lexical.search(
                con, query,
                k=max(k * 4, 24),
                filter_sql=anchor_sql,
                filter_params=anchor_params,
            )
        except Exception:                            # noqa: BLE001
            lexical_results = []

    if lexical_results:
        # RRF merge by (path, ord). Vector list keeps its enriched fields;
        # lexical-only items get a stub envelope with just (path, ord, ...).
        merged = _lexical.rrf_merge(
            out,
            lexical_results,
            vector_weight=CONFIG.lexical_vector_weight,
            lexical_weight=CONFIG.lexical_lexical_weight,
        )
        # Phase E refinement (2026-05-16): enrich pure-lexical-only hits with
        # a second-pass node + chunk fetch. These are chunks whose body
        # matches the query lexically but ranked outside the vector top-K —
        # without this pass we'd drop them and lose the lexical-anchor signal
        # they carry (e.g. SEC 10-Q chunks with the exact operator phrase).
        # Cost: one cache.get_node + one cache.get_chunk_at_ord per pure-lex
        # hit (~sub-ms each on the live corpus, bounded by lexical k=24-32).
        #
        # Decay ranks are recomputed over the COMBINED set (vector + newly-
        # enriched lex-only) so a click-capital video that surfaces via lex
        # alone still competes in the same per-author ranking as click-capital
        # videos that hit via vector. Without this re-pass, pure-lex hits get
        # rank=None → weight=1.0 → over-rank vs their ladder siblings.
        lex_only_nodes: list[dict] = []
        lex_only_rows: list[tuple[dict, dict, dict]] = []  # (row, node, chunk)
        for row in merged:
            if "text" in row:
                continue
            path = row.get("path")
            ord_ = row.get("ord", 0)
            if path is None:
                continue
            node = _cache.get_node(con, path)
            if node is None:
                continue
            chunk = _cache.get_chunk_at_ord(con, path, int(ord_))
            if chunk is None:
                continue
            lex_only_nodes.append(node)
            lex_only_rows.append((row, node, chunk))

        # Re-rank over the combined node pool so lex-only hits participate in
        # author groups + kind_overrides exactly like vector hits do.
        if lex_only_nodes and CONFIG.decay_mode == "ranked_grouped":
            combined_ranks = _decay.assign_ranks(
                seen_nodes + lex_only_nodes,
                group_key=CONFIG.decay_group_key,
                kind_overrides=CONFIG.decay_kind_overrides,
            )
        else:
            combined_ranks = ranks

        enriched: list[dict] = []
        for row in merged:
            if "text" in row:
                # Vector side already enriched. Possibly update its decay
                # rank if combined-pool re-ranking changed things.
                if combined_ranks is not ranks:
                    new_rank = combined_ranks.get(row["path"])
                    if new_rank != row.get("decay_rank"):
                        new_decay = _decay.weight_for(
                            {**row, "evergreen": row.get("evergreen")},
                            rank=new_rank,
                        )
                        if new_decay <= 0.0:
                            continue
                        row = {
                            **row,
                            "decay_rank": new_rank,
                            "decay_weight": new_decay,
                            "score": row.get("similarity", 0.0) * new_decay,
                        }
                enriched.append(row)
                continue
        # Build lex-only enriched rows
        for row, node, chunk in lex_only_rows:
            path = row.get("path")
            node_rank = combined_ranks.get(path)
            decay = _decay.weight_for(node, rank=node_rank)
            if decay <= 0.0:
                continue
            placeholder_sim = float(row.get("lexical_score") or 0.0)
            score = placeholder_sim * decay
            enriched.append({
                **row,
                "text": chunk["text"],
                "section": chunk.get("section"),
                "title": node.get("title"),
                "kind": node.get("kind"),
                "author": node.get("author"),
                "published_at": node.get("published_at"),
                "horizon_months": node.get("horizon_months"),
                "evergreen": node.get("evergreen"),
                "tags": node.get("tags"),
                "similarity": placeholder_sim,
                "decay_weight": decay,
                "decay_rank": node_rank,
                "score": score,
                "lexical_only": True,        # debug breadcrumb
            })
        out = enriched

    # Hybrid re-rank BEFORE the [:k] cut so rank changes affect inclusion.
    use_hybrid = CONFIG.graph_enabled if hybrid is None else hybrid
    if use_hybrid:
        out = _hybrid.rerank(out, con, _hybrid.from_config())

    # Snapshot the fully-scored candidate set BEFORE the top-k cut so the
    # retrieval log can record which eligible candidates were dropped purely
    # by rank (the "had it, didn't surface" delta — limitation C1).
    pre_cut = list(out)
    out = out[:k]
    _maybe_log(
        con, query=query, mode=mode, k=k, parsed=parsed,
        eligible_count=eligible_count, pre_cut=pre_cut, surfaced=out,
        enabled=log,
    )

    # Extractive teaser: 2 sentences from each chunk most relevant to the
    # query. Reuses the already-loaded BGE encoder. Despite the original
    # comment of "~50ms per chunk", real-world cost is closer to 1-3s per
    # chunk because every sentence (typically 25-40 per chunk) gets a
    # separate BGE forward pass. This is the dominant latency of /search.
    #
    # Skipped entirely when ``excerpts=False`` — MCP/bundle callers get the
    # full chunk ``text`` already, so excerpts are dead weight on that path.
    if excerpts:
        for r in out:
            try:
                r["excerpt_sentences"] = _excerpt.select_top_sentences(
                    query, r["text"], k=2
                )
            except Exception:                            # noqa: BLE001
                r["excerpt_sentences"] = []
    return out


def similar_to_node(con, path: str, *, k: int = 5, exclude_self: bool = True) -> list[dict]:
    """Find the k most-similar nodes to a given vault path. Uses the node's
    first chunk as the query embedding."""
    rows = list(con.execute(
        "SELECT id FROM vault_chunk WHERE path = ? ORDER BY ord LIMIT 1",
        (path,),
    ))
    if not rows:
        return []
    chunk_id = rows[0][0]
    blob_rows = list(con.execute(
        "SELECT embedding FROM vault_chunk_vec WHERE chunk_id = ?",
        (chunk_id,),
    ))
    if not blob_rows:
        return []
    qblob = blob_rows[0][0]
    raw_k = max(k * 8, 40)
    knn = list(con.execute(
        """
        SELECT v.chunk_id, v.distance, c.path
        FROM vault_chunk_vec v
        JOIN vault_chunk c ON c.id = v.chunk_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (qblob, raw_k),
    ))
    seen: set[str] = set()
    if exclude_self:
        seen.add(path)
    out: list[dict] = []
    for chunk_id_, dist, npath in knn:
        if npath in seen:
            continue
        seen.add(npath)
        sim = 1.0 - float(dist)
        out.append({"path": npath, "similarity": sim})
        if len(out) >= k:
            break
    return out
