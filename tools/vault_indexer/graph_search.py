"""Iterative-deepening graph search.

Seeds from top-K vector matches, then expands via ``vault_edge`` neighbors
hop by hop. Each hop's new candidates are scored against the query using
``vec_distance_cosine`` (via sqlite-vec, no bulk numpy load) and beam-pruned
to bound growth.

Stops early when the candidate pool reaches ``target_k`` AND average
similarity is ≥ ``quality_floor`` — most queries converge in 1-2 hops.

Edge kinds traversed: ALL (parent / wikilink / citation / similarity_temporal).
This is broader than the centrality computation, which excludes parent and
similarity_temporal — for *traversal*, all edges are relevant (sibling
chapters via parent, daily-thesis chronology via temporal). The PageRank /
centrality scoring still filters appropriately when hybrid re-ranking
applies the final ordering.

Memory profile: per-query we touch O(beam_width × max_hops × seed_count)
embeddings — typically <100. No bulk load.
"""
from __future__ import annotations

import logging
import struct
from typing import Optional

from . import cache as _cache
from . import decay as _decay
from . import embed as _embed
from . import hybrid as _hybrid
from . import retrieval_log as _rlog
from .config import CONFIG

log = logging.getLogger("vault-indexer.graph_search")


# ---------------------------------------------------------------------------
# Deep mode (retrieval-depth-and-debiasing-program, Phase 1)
# ---------------------------------------------------------------------------
#
# Deep mode is the "retrieve wide, filter late" path. It runs on-demand from a
# Claude Code session (no API, relaxed latency budget) where the fast path's
# <100-embedding budget does not apply. Two principles distinguish it from the
# fast graph_search:
#
#   1. Nothing vanishes silently. A candidate evaluated and rejected is
#      RETURNED with a reason (``drop_reason``), not dropped. The judgment
#      layer (the LLM in-session) does the final filtering with full
#      visibility — the operator's core ask: "data not filtered out before
#      being evaluated."
#   2. Decay is a FEATURE, not a filter (limitation A4). Fast search drops
#      decay<=0 rows (e.g. SEC filings past the keep-2 cap); deep mode keeps
#      them, flagged ``decay_zero``, so an old-but-dispositive filing can still
#      reach the judgment layer.

# Deep-mode parameter defaults — wider than fast search on every axis.
DEEP_DEFAULTS = {
    "k": 50,
    "max_hops": 4,
    "seed_count": 8,
    "beam_width": 12,
    "prune_threshold": 0.30,
    "target_k": 50,
}


def classify_candidates(
    retained: list[dict], pruned: list[dict]
) -> dict:
    """Pure filter-late split. No DB, no model — unit-testable.

    ``retained`` = candidates that cleared the per-hop prune floor (each a
    materialized result dict with at least ``path``, ``score``,
    ``decay_weight``, ``hop``). ``pruned`` = candidates evaluated but below the
    floor (``path``, ``similarity``, ``hop``).

    Returns ``{"surfaced": [...], "dropped": [...]}`` where:
      * surfaced = retained, sorted by score desc, with a ``decay_zero`` flag
        attached (kept, NOT dropped — A4) and a ``retain_reason``.
      * dropped = pruned, each stamped with ``drop_reason`` so the retrieval
        log + judgment layer can see exactly what was considered and rejected.
    Nothing is discarded by this function.
    """
    for p in pruned:
        p.setdefault("drop_reason", "below_prune_threshold")
    for r in retained:
        decay = r.get("decay_weight")
        r["decay_zero"] = (decay is not None and decay <= 0.0)
        # retain_reason makes the keep-decision auditable alongside drop_reason.
        if r.get("hop", 0) == 0:
            r.setdefault("retain_reason", "seed")
        elif r["decay_zero"]:
            r.setdefault("retain_reason", "kept_despite_decay_zero")
        else:
            r.setdefault("retain_reason", "above_prune_floor")
    surfaced = sorted(retained, key=lambda r: r.get("score") or 0.0, reverse=True)
    return {"surfaced": surfaced, "dropped": list(pruned)}


def _seed_paths(con, qblob: bytes, k: int) -> list[tuple[str, float]]:
    """Top-k vector seeds, deduped to one chunk per path."""
    raw_k = max(k * 4, 24)
    rows = list(con.execute(
        """
        SELECT v.distance, c.path
        FROM vault_chunk_vec v
        JOIN vault_chunk c ON c.id = v.chunk_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (qblob, raw_k),
    ))
    seen: set[str] = set()
    seeds: list[tuple[str, float]] = []
    for dist, path in rows:
        if path in seen:
            continue
        seen.add(path)
        seeds.append((path, 1.0 - float(dist)))
        if len(seeds) >= k:
            break
    return seeds


def _neighbors(con, path: str) -> set[str]:
    """All neighbors via vault_edge (undirected union over all kinds)."""
    out: set[str] = set()
    for r in con.execute(
        """
        SELECT dst_path FROM vault_edge WHERE src_path = ?
        UNION
        SELECT src_path FROM vault_edge WHERE dst_path = ?
        """,
        (path, path),
    ):
        out.add(r[0])
    return out


def _score_path_vs_query(con, qblob: bytes, path: str) -> Optional[tuple[int, int, str, str, float]]:
    """Find the best-matching chunk for ``path`` against the query.

    Returns ``(chunk_id, ord, text, section, distance)`` or None if path has
    no chunks (e.g. folder_context kind).
    """
    row = con.execute(
        """
        SELECT c.id, c.ord, c.text, c.section, vec_distance_cosine(v.embedding, ?) as dist
        FROM vault_chunk_vec v JOIN vault_chunk c ON c.id = v.chunk_id
        WHERE c.path = ? ORDER BY dist LIMIT 1
        """,
        (qblob, path),
    ).fetchone()
    return row if row else None


def graph_search(
    con,
    query: str,
    *,
    k: int = 8,
    max_hops: int = 4,
    seed_count: int = 3,
    beam_width: int = 5,
    prune_threshold: float = 0.50,
    quality_floor: float = 0.65,
    target_k: int = 10,
) -> dict:
    """Iterative-deepening graph search.

    Returns ``{query, hops_used, seed_paths, candidates_per_hop, results}``
    where ``results`` mirrors `/search`'s shape (with `hybrid_score` when
    hybrid is effective).
    """
    qvec = _embed.encode_query(query)
    qblob = struct.pack(f"{len(qvec)}f", *qvec)

    seeds = _seed_paths(con, qblob, seed_count)
    if not seeds:
        return {
            "query": query,
            "hops_used": 0,
            "seed_paths": [],
            "candidates_per_hop": [0],
            "results": [],
        }

    candidates: dict[str, float] = {p: s for p, s in seeds}
    frontier: list[str] = list(candidates.keys())
    candidates_per_hop: list[int] = [len(candidates)]
    hops_used = 0

    for hop in range(1, max_hops + 1):
        neighbor_paths: set[str] = set()
        for path in frontier:
            for npath in _neighbors(con, path):
                if npath not in candidates:
                    neighbor_paths.add(npath)
        if not neighbor_paths:
            break

        new_nodes: list[tuple[str, float]] = []
        for npath in neighbor_paths:
            row = con.execute(
                """
                SELECT vec_distance_cosine(v.embedding, ?)
                FROM vault_chunk_vec v JOIN vault_chunk c ON c.id = v.chunk_id
                WHERE c.path = ? ORDER BY 1 LIMIT 1
                """,
                (qblob, npath),
            ).fetchone()
            if row is None:
                continue
            sim = 1.0 - float(row[0])
            if sim >= prune_threshold:
                new_nodes.append((npath, sim))

        if not new_nodes:
            break

        beam_cap = max(beam_width * max(1, len(frontier)), beam_width)
        new_nodes.sort(key=lambda t: -t[1])
        new_nodes = new_nodes[:beam_cap]
        for npath, sim in new_nodes:
            candidates[npath] = sim
        frontier = [p for p, _ in new_nodes]
        hops_used = hop
        candidates_per_hop.append(len(candidates))

        # Stop early if pool is large enough AND average quality is high.
        if len(candidates) >= target_k:
            avg = sum(candidates.values()) / len(candidates)
            if avg >= quality_floor:
                break

    # Materialize results: best-matching chunk per path + hybrid score.
    results: list[dict] = []
    for path, _candidate_sim in candidates.items():
        chunk_row = _score_path_vs_query(con, qblob, path)
        if chunk_row is None:
            continue
        _cid, ord_, text, section, dist = chunk_row
        node = _cache.get_node(con, path)
        if node is None:
            continue
        sim = 1.0 - float(dist)
        decay = _decay.weight_for(node)
        results.append({
            "path": path,
            "ord": ord_,
            "text": text,
            "section": section,
            "title": node.get("title"),
            "kind": node.get("kind"),
            "author": node.get("author"),
            "published_at": node.get("published_at"),
            "horizon_months": node.get("horizon_months"),
            "tags": node.get("tags"),
            "similarity": sim,
            "decay_weight": decay,
            "score": sim * decay,
        })

    if CONFIG.graph_enabled:
        results = _hybrid.rerank(results, con, _hybrid.from_config())
    else:
        results.sort(key=lambda r: r["score"], reverse=True)

    return {
        "query": query,
        "hops_used": hops_used,
        "seed_paths": [p for p, _ in seeds],
        "candidates_per_hop": candidates_per_hop,
        "results": results[:k],
    }


def deep_search(
    con,
    query: str,
    *,
    k: int = 50,
    max_hops: int = 4,
    seed_count: int = 8,
    beam_width: int = 12,
    prune_threshold: float = 0.30,
    target_k: int = 50,
    disable_early_stop: bool = True,
    log: bool = True,
) -> dict:
    """Filter-late deep retrieval (Phase 1).

    Walks the graph wider and deeper than the fast path, then returns the
    FULL evaluated candidate set — retained AND pruned — each annotated with
    hop distance, decay (as a feature), and a retain/drop reason. The
    judgment layer filters; the retriever does not pre-filter.

    Returns ``{query, mode, hops_used, seed_paths, candidates_per_hop,
    params, results, pruned}`` where ``results`` are the retained candidates
    (sorted) and ``pruned`` are evaluated-but-rejected candidates with
    reasons. Both are logged to ``retrieval_log`` under ``mode="deep"``.
    """
    qvec = _embed.encode_query(query)
    qblob = struct.pack(f"{len(qvec)}f", *qvec)

    params = {
        "k": k, "max_hops": max_hops, "seed_count": seed_count,
        "beam_width": beam_width, "prune_threshold": prune_threshold,
        "target_k": target_k, "disable_early_stop": disable_early_stop,
    }

    seeds = _seed_paths(con, qblob, seed_count)
    if not seeds:
        if log:
            _rlog.record(
                con, query=query, mode="deep", domain=CONFIG.domain, k=k,
                eligible_count=0, surfaced=[], dropped=[],
            )
        return {
            "query": query, "mode": "deep", "hops_used": 0,
            "seed_paths": [], "candidates_per_hop": [0],
            "params": params, "results": [], "pruned": [],
        }

    # hop_of records the hop at which each retained candidate entered the pool.
    candidates: dict[str, float] = {p: s for p, s in seeds}
    hop_of: dict[str, int] = {p: 0 for p, _ in seeds}
    # pruned_raw: candidates evaluated at some hop but below the prune floor.
    # Keyed by path so a later, better hop can rescue one out of the pruned set.
    pruned_raw: dict[str, dict] = {}
    frontier: list[str] = list(candidates.keys())
    candidates_per_hop: list[int] = [len(candidates)]
    hops_used = 0

    for hop in range(1, max_hops + 1):
        neighbor_paths: set[str] = set()
        for path in frontier:
            for npath in _neighbors(con, path):
                if npath not in candidates:
                    neighbor_paths.add(npath)
        if not neighbor_paths:
            break

        new_nodes: list[tuple[str, float]] = []
        for npath in neighbor_paths:
            row = con.execute(
                """
                SELECT vec_distance_cosine(v.embedding, ?)
                FROM vault_chunk_vec v JOIN vault_chunk c ON c.id = v.chunk_id
                WHERE c.path = ? ORDER BY 1 LIMIT 1
                """,
                (qblob, npath),
            ).fetchone()
            if row is None:
                continue
            sim = 1.0 - float(row[0])
            if sim >= prune_threshold:
                new_nodes.append((npath, sim))
                # If it had been pruned at an earlier hop, it's rescued now.
                pruned_raw.pop(npath, None)
            elif npath not in pruned_raw:
                # Record the rejection instead of silently dropping it.
                pruned_raw[npath] = {
                    "path": npath, "similarity": sim, "hop": hop,
                    "drop_reason": "below_prune_threshold",
                }

        if not new_nodes:
            break

        beam_cap = max(beam_width * max(1, len(frontier)), beam_width)
        new_nodes.sort(key=lambda t: -t[1])
        kept = new_nodes[:beam_cap]
        # Beam overflow is also a rejection-with-reason, not a silent drop.
        for npath, sim in new_nodes[beam_cap:]:
            if npath not in pruned_raw:
                pruned_raw[npath] = {
                    "path": npath, "similarity": sim, "hop": hop,
                    "drop_reason": "beam_overflow",
                }
        for npath, sim in kept:
            candidates[npath] = sim
            hop_of[npath] = hop
        frontier = [p for p, _ in kept]
        hops_used = hop
        candidates_per_hop.append(len(candidates))

        # Early-stop is DISABLED by default in deep mode — we want full depth.
        if not disable_early_stop and len(candidates) >= target_k:
            avg = sum(candidates.values()) / len(candidates)
            if avg >= quality_floor:  # noqa: F821 — only reached when enabled
                break

    # Materialize ALL retained candidates. Unlike fast search, decay<=0 rows
    # are KEPT (flagged downstream) — recency truncation must not pre-filter
    # the judgment layer (A4).
    retained: list[dict] = []
    for path in candidates:
        chunk_row = _score_path_vs_query(con, qblob, path)
        if chunk_row is None:
            continue
        _cid, ord_, text, section, dist = chunk_row
        node = _cache.get_node(con, path)
        if node is None:
            continue
        sim = 1.0 - float(dist)
        decay = _decay.weight_for(node)
        retained.append({
            "path": path,
            "ord": ord_,
            "text": text,
            "section": section,
            "title": node.get("title"),
            "kind": node.get("kind"),
            "author": node.get("author"),
            "published_at": node.get("published_at"),
            "horizon_months": node.get("horizon_months"),
            "tags": node.get("tags"),
            "similarity": sim,
            "decay_weight": decay,
            "hop": hop_of.get(path, 0),
            # Score keeps decay as a soft signal but never zeroes a candidate
            # out of existence: a decay-0 row still carries its similarity.
            "score": sim * (decay if decay > 0 else 1.0),
        })

    classified = classify_candidates(retained, list(pruned_raw.values()))
    surfaced = classified["surfaced"][:k]
    pruned = classified["dropped"]

    if log:
        _rlog.record(
            con, query=query, mode="deep", domain=CONFIG.domain, k=k,
            eligible_count=len(retained) + len(pruned),
            surfaced=surfaced, dropped=pruned,
        )

    return {
        "query": query,
        "mode": "deep",
        "hops_used": hops_used,
        "seed_paths": [p for p, _ in seeds],
        "candidates_per_hop": candidates_per_hop,
        "params": params,
        "results": surfaced,
        "pruned": pruned,
    }
