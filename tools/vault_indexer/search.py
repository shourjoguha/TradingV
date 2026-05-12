"""Retrieval — embed query, KNN over sqlite-vec, apply decay weighting."""
from __future__ import annotations

import json
import struct
from typing import Optional

from . import cache as _cache
from . import decay as _decay
from . import embed as _embed
from . import hybrid as _hybrid
from .config import CONFIG


def search(
    con,
    query: str,
    *,
    k: int = 8,
    hypothesis_paths: Optional[list[str]] = None,
    hybrid: Optional[bool] = None,
) -> list[dict]:
    """Vector search with optional hybrid re-rank.

    ``hybrid`` parameter (None → CONFIG.graph_enabled) controls whether
    graph signals (citation_rank, centrality, recency boost) re-rank the
    results. The original ``score`` field is always preserved; ``hybrid_score``
    is added as a sibling key when re-ranking is effective.

    Below the ``min_edges_for_hybrid`` floor, hybrid is a no-op even when
    enabled — preserves baseline behavior on cold-start corpora.
    """
    from . import excerpt as _excerpt

    qvec = _embed.encode_query(query)
    qblob = struct.pack(f"{len(qvec)}f", *qvec)

    # Ask vec0 for top (k * 4) by raw cosine; we'll re-rank with decay.
    raw_k = max(k * 4, 24)
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
    if not rows:
        return []

    # Distance is cosine distance ∈ [0, 2]; convert to similarity ∈ [-1, 1].
    out: list[dict] = []
    for chunk_id, dist, path, ord_, text, section in rows:
        if hypothesis_paths is not None and path not in hypothesis_paths:
            continue
        node = _cache.get_node(con, path)
        if node is None:
            continue
        sim = 1.0 - float(dist)              # cosine distance → similarity
        decay = _decay.weight_for(node)
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
            "tags": node.get("tags"),
            "similarity": sim,
            "decay_weight": decay,
            "score": score,
        })
    out.sort(key=lambda r: r["score"], reverse=True)

    # Hybrid re-rank BEFORE the [:k] cut so rank changes affect inclusion.
    use_hybrid = CONFIG.graph_enabled if hybrid is None else hybrid
    if use_hybrid:
        out = _hybrid.rerank(out, con, _hybrid.from_config())

    out = out[:k]

    # Extractive teaser: 2 sentences from each chunk most relevant to the
    # query. Reuses the already-loaded BGE encoder; ~50ms per chunk.
    # Returned alongside the full ``text`` so the UI can offer expand.
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
