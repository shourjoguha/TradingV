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
from .config import CONFIG

log = logging.getLogger("vault-indexer.graph_search")


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
