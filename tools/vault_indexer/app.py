"""vault-indexer FastAPI app — port 8001.

Endpoints:
  GET  /health
  POST /reload                 — full vault rescan (idempotent)
  GET  /node/{path:path}       — node metadata + body
  GET  /search?q=&k=           — KNN with decay
  GET  /traverse/{path:path}?depth=2  — local subgraph
  POST /promote                — apply ticks from _review-queue.md, regenerate it
  POST /apply-renames          — apply pending RENAMES from _taxonomy.md
  POST /regenerate-review      — gather suggestions and rewrite the queue file
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query

from . import cache as _cache
from . import graph_compute as _graph_compute
from . import graph_search as _graph_search
from . import graph_state as _graph_state
from . import indexer as _indexer
from . import lexical as _lexical
from . import query_parse as _qp
from . import renames as _renames
from . import research_hook as _research_hook
from . import review as _review
from . import search as _search
from . import taxonomy as _tax
from .config import CONFIG

logger = logging.getLogger("vault-indexer")
logging.basicConfig(level=logging.INFO)


_CON = None


def _con():
    global _CON
    if _CON is None:
        _CON = _cache.init(CONFIG.db_path, CONFIG.embedding_dim)
    return _CON


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Validate the vault path; create cache file lazily.
    if not CONFIG.vault_path.exists():
        logger.error("vault not found at %s", CONFIG.vault_path)
        raise RuntimeError(f"vault not found at {CONFIG.vault_path}")
    con = _con()
    # Phase E Commit 2: backfill `evergreen` column on existing rows so the
    # ranked-grouped decay model picks up correct classifications without a
    # full re-ingest. Idempotent: skips rows already non-NULL.
    try:
        updated = _cache.backfill_evergreen(con, CONFIG.is_evergreen_path)
        if updated:
            logger.info("evergreen backfill: classified %d nodes", updated)
    except Exception as e:                              # noqa: BLE001
        logger.warning("evergreen backfill failed (non-fatal): %s", e)
    # Phase E Commit 4: ensure FTS5 lexical index is populated. On a fresh
    # cache or a cache that pre-dates Commit 4, the index will be empty
    # until /reload runs; rebuild here so the first /search request has
    # both signals available.
    try:
        existing_fts_rows = list(con.execute(
            "SELECT COUNT(*) FROM vault_chunk_fts"
        ))[0][0]
        chunk_rows = list(con.execute(
            "SELECT COUNT(*) FROM vault_chunk"
        ))[0][0]
        if chunk_rows > 0 and existing_fts_rows < chunk_rows:
            _lexical.rebuild(con)
    except Exception as e:                              # noqa: BLE001
        logger.warning("FTS5 rebuild failed (non-fatal): %s", e)
    logger.info(
        "vault-indexer up — vault=%s db=%s model=%s decay=%s lexical=%s",
        CONFIG.vault_path, CONFIG.db_path, CONFIG.embedding_model,
        CONFIG.decay_mode, "on" if CONFIG.lexical_enabled else "off",
    )
    yield


app = FastAPI(lifespan=lifespan, title="vault-indexer")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "vault": str(CONFIG.vault_path),
        "db": str(CONFIG.db_path),
        "model": CONFIG.embedding_model,
        "embedding_dim": CONFIG.embedding_dim,
    }


@app.post("/reload")
async def reload_vault():
    """Apply pending RENAMES, full rescan, regenerate review queue.

    Also schedules a debounced graph recompute. The recompute fires after
    `CONFIG.graph_debounce_seconds` of quiet — bursts of /reload calls
    collapse into one recompute. Recompute runs off the event loop in
    a background thread; /reload returns as soon as the rescan completes.
    """
    rename_log = _renames.apply_renames(
        CONFIG.vault_path, CONFIG.vault_path / CONFIG.taxonomy_file
    )
    _indexer.reload_alias_map()
    stats = _indexer.full_rescan(_con())
    tax = _tax.parse_file(CONFIG.vault_path / CONFIG.taxonomy_file)
    suggestions = _review.gather_suggestions(_con(), vocabulary=tax.tags)
    suggestions["rename_log"] = rename_log
    _review.write(CONFIG.vault_path, _review.render(suggestions))
    # Newly-ingested Filings/Research may have introduced tickers not in the
    # cached lexicon. Force a refresh so the next /search request sees them.
    _search.reset_ticker_lexicon()
    # Phase E Commit 4: rebuild FTS5 lexical index — full_rescan may have
    # added/changed chunks. Cost is hundreds of ms on the live finance corpus.
    try:
        fts_rows = _lexical.rebuild(_con())
    except Exception as e:                              # noqa: BLE001
        logger.warning("FTS5 rebuild failed (non-fatal): %s", e)
        fts_rows = 0
    if CONFIG.graph_enabled:
        _graph_state.schedule(_con(), debounce_seconds=CONFIG.graph_debounce_seconds)
    return {
        **stats, "renames": rename_log,
        "graph_scheduled": CONFIG.graph_enabled, "fts_indexed": fts_rows,
    }


@app.post("/recompute_graph")
async def recompute_graph_endpoint():
    """Synchronously run graph recompute. Bypasses the debounce window —
    used by ops scripts and the nightly safety-net cron. Idempotent.
    """
    if not CONFIG.graph_enabled:
        return {"status": "disabled"}
    return _graph_compute.recompute(_con())


@app.get("/node/{path:path}")
async def get_node(path: str):
    node = _cache.get_node(_con(), path)
    if node is None:
        raise HTTPException(404, f"node not found: {path}")
    return node


@app.get("/chunks/{path:path}")
async def get_chunks_endpoint(
    path: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Pre-chunked content for a vault doc, ordered by `ord`. Paginated.

    Long-form transcripts (200KB+) chunk into ~60 segments of ~600 words each.
    Use this instead of /node when you need to walk a long doc sequentially
    (e.g. for whole-episode summarisation) — avoids the timeout that comes
    from JSON-encoding a 200KB body in one shot.

    Returns: { path, meta, total_chunks, offset, limit, has_more, chunks: [...] }
    Where each chunk is { ord, text, section }.

    404 if the node itself isn't in the cache. Returns 200 with empty chunks
    list when the node exists but is intentionally chunkless (e.g.
    kind='folder_context').
    """
    con = _con()
    node = _cache.get_node(con, path)
    if node is None:
        raise HTTPException(404, f"node not found: {path}")
    total = _cache.count_chunks(con, path)
    chunks = _cache.get_chunks(con, path, offset=offset, limit=limit)
    return {
        "path": path,
        "meta": {
            "kind": node.get("kind"),
            "title": node.get("title"),
            "author": node.get("author"),
            "published_at": node.get("published_at"),
            "horizon_months": node.get("horizon_months"),
            "tags": node.get("tags") or [],
            "last_indexed_at": node.get("last_indexed_at"),
        },
        "total_chunks": total,
        "offset": offset,
        "limit": limit,
        "returned": len(chunks),
        "has_more": (offset + len(chunks)) < total,
        "next_offset": (offset + len(chunks)) if (offset + len(chunks)) < total else None,
        "chunks": chunks,
    }


@app.get("/search")
async def search_endpoint(
    q: str = Query(..., min_length=1),
    k: int = Query(8, ge=1, le=50),
    hybrid: bool | None = Query(None, description="Override CONFIG.graph_enabled for this request. Pass false to compare hybrid vs vector ranking."),
    excerpts: bool = Query(
        True,
        description=(
            "When true (default), each result includes `excerpt_sentences` — "
            "the 2 sentences best matching the query, computed by re-encoding "
            "each chunk's sentences with BGE. Costs O(k * sentences_per_chunk) "
            "BGE forwards (~1-3s per chunk). UI consumers want this; MCP/bundle "
            "consumers already get `text` and should pass `excerpts=false` for "
            "sub-second latency."
        ),
    ),
    parse: bool = Query(
        True,
        description=(
            "When true (default), the query is run through query_parse to "
            "extract tickers / kinds / since anchors and pre-filter the KNN "
            "pool. When no anchors detect, the filter is a no-op (legacy "
            "behaviour). Set false to skip anchor extraction (pure vector)."
        ),
    ),
):
    con = _con()
    # Auto-parse the query so the response can echo back what anchors were
    # detected. Result is also passed through to search() for the pre-filter.
    parsed = (
        _qp.parse(q, ticker_lexicon=_search._ticker_lexicon(con))
        if parse else None
    )
    return {
        "query": q,
        "k": k,
        "parsed": (
            None if parsed is None else {
                "tickers": parsed.tickers,
                "kinds": parsed.kinds,
                "since": parsed.since.isoformat() if parsed.since else None,
                "raw_terms": parsed.raw_terms,
                "has_anchors": parsed.has_anchors(),
            }
        ),
        "results": _search.search(
            con, q, k=k, hybrid=hybrid, excerpts=excerpts, parse=parse,
        ),
    }


@app.get("/graph_search")
async def graph_search_endpoint(
    q: str = Query(..., min_length=1),
    k: int = Query(8, ge=1, le=50),
    max_hops: int = Query(4, ge=1, le=6),
    seed_count: int = Query(3, ge=1, le=10),
    beam_width: int = Query(5, ge=1, le=20),
):
    """Iterative-deepening graph traversal seeded by vector similarity.

    Returns the same per-result shape as /search plus debug fields
    (`hops_used`, `seed_paths`, `candidates_per_hop`). Below the
    `min_edges_for_hybrid` floor, the hybrid re-rank is a no-op and
    results are scored by vector similarity alone.
    """
    return _graph_search.graph_search(
        _con(), q,
        k=k, max_hops=max_hops, seed_count=seed_count, beam_width=beam_width,
    )


@app.get("/deep_search")
async def deep_search_endpoint(
    q: str = Query(..., min_length=1),
    k: int = Query(50, ge=1, le=200),
    max_hops: int = Query(4, ge=1, le=6),
    seed_count: int = Query(8, ge=1, le=20),
    beam_width: int = Query(12, ge=1, le=40),
    prune_threshold: float = Query(0.30, ge=0.0, le=1.0),
    target_k: int = Query(50, ge=1, le=200),
    disable_early_stop: bool = Query(True),
):
    """Filter-late deep retrieval (retrieval-depth Phase 1).

    Wider/deeper than /graph_search and returns the FULL evaluated candidate
    set: ``results`` (retained, each with hop + decay-as-feature + retain
    reason) PLUS ``pruned`` (evaluated-but-rejected, each with a drop reason).
    Nothing is filtered out before the judgment layer sees it — that's the
    point. Meant to be called on-demand from a Claude Code session
    (``/rx-deep-retrieve``), not on the always-on fast path.
    """
    return _graph_search.deep_search(
        _con(), q,
        k=k, max_hops=max_hops, seed_count=seed_count, beam_width=beam_width,
        prune_threshold=prune_threshold, target_k=target_k,
        disable_early_stop=disable_early_stop,
    )


@app.post("/folder-context")
async def folder_context_endpoint(payload: dict = Body(...)):
    """Given a list of evidence vault paths, return the operator-authored
    `_index.md` (kind='folder_context') vignettes that apply along their
    ancestor chain. Bundle assembler calls this after `/search`."""
    paths = payload.get("paths") or []
    if not isinstance(paths, list):
        raise HTTPException(400, "paths must be a list")
    items = _cache.folder_contexts_for(_con(), [str(p) for p in paths])
    return {"items": items}


@app.get("/traverse/{path:path}")
async def traverse_endpoint(path: str, depth: int = Query(1, ge=1, le=3)):
    """Return the path's node plus first-/second-degree neighbours.

    Edges considered: explicit (parent / wikilink) AND auto-similarity
    (top-K similar nodes).
    """
    node = _cache.get_node(_con(), path)
    if node is None:
        raise HTTPException(404, f"node not found: {path}")
    visited: dict[str, dict] = {path: node}
    frontier = [path]
    for _ in range(depth):
        next_frontier: list[str] = []
        for cur in frontier:
            # Explicit edges.
            for r in _con().execute(
                "SELECT dst_path, kind, weight FROM vault_edge WHERE src_path = ? "
                "UNION ALL "
                "SELECT src_path, kind, weight FROM vault_edge WHERE dst_path = ?",
                (cur, cur),
            ):
                dst, _kind, _w = r
                if dst in visited:
                    continue
                n = _cache.get_node(_con(), dst)
                if n is not None:
                    visited[dst] = n
                    next_frontier.append(dst)
            # Implicit similarity edges.
            for sim in _search.similar_to_node(_con(), cur, k=3, exclude_self=True):
                p = sim["path"]
                if p in visited:
                    continue
                n = _cache.get_node(_con(), p)
                if n is not None:
                    visited[p] = n
                    next_frontier.append(p)
        frontier = next_frontier
        if not frontier:
            break
    return {"root": path, "depth": depth, "nodes": list(visited.values())}


@app.post("/promote")
async def promote_endpoint():
    """Read ticks from `_review-queue.md`, apply them, regenerate the queue.

    Also scans `Research/*.md` for ticked Approve/Dismiss boxes and
    fires the corresponding TradingView API call.
    """
    text = _review.read(CONFIG.vault_path)
    ticks = _review.parse_ticks(text)
    counts = _review.promote(_con(), CONFIG.vault_path, ticks) if ticks else {}
    research_counts = _research_hook.scan_and_apply(CONFIG.vault_path)
    # Re-scan so applied tags + Research ticks are reflected in the cache.
    _indexer.full_rescan(_con())
    tax = _tax.parse_file(CONFIG.vault_path / CONFIG.taxonomy_file)
    suggestions = _review.gather_suggestions(_con(), vocabulary=tax.tags)
    _review.write(CONFIG.vault_path, _review.render(suggestions))
    return {"applied": counts, "research": research_counts}


@app.post("/apply-renames")
async def apply_renames_endpoint():
    log = _renames.apply_renames(
        CONFIG.vault_path, CONFIG.vault_path / CONFIG.taxonomy_file
    )
    _indexer.full_rescan(_con())
    return {"renames": log}


@app.post("/regenerate-review")
async def regenerate_review_endpoint():
    tax = _tax.parse_file(CONFIG.vault_path / CONFIG.taxonomy_file)
    suggestions = _review.gather_suggestions(_con(), vocabulary=tax.tags)
    _review.write(CONFIG.vault_path, _review.render(suggestions))
    return {"ok": True, "vocabulary_size": len(tax.tags)}
