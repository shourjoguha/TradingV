"""Hybrid scorer — re-rank vector search results with graph signals.

Layers ``citation_rank``, ``centrality`` (from `vault_node`, computed by
``graph_compute.recompute()``) and a ``recency_boost`` on top of the
existing ``cos_sim · decay`` score.

Formula (after graceful-degradation folding):

    hybrid_score = α'·base_score + β'·citation_rank + γ'·centrality + recency

where:
- ``base_score`` is the existing ``score`` field (``sim·decay``).
- ``α' = α + (β if citation_rank IS NULL) + (γ if centrality IS NULL)``
  so missing graph signals don't penalize results — the weight folds back
  into the dominant semantic term.
- ``β' = β if citation_rank IS NOT NULL else 0``
- ``γ' = γ if centrality IS NOT NULL else 0``
- ``recency = recency_boost_amount`` if `last_indexed_at` (or the
  ``published_at`` fallback) is within ``recency_boost_days``, else 0.

Graceful-degradation floor: if total edges in the DB < ``min_edges``,
``rerank()`` is a no-op — results return unchanged, no `hybrid_score`
field added. Cold-start corpora (sparse fitness/nutrition graphs)
behave identically to the pre-graph baseline.

The scorer **never overwrites the `score` field**; `hybrid_score` is
added as a sibling key. Existing consumers that ignore the new field
see byte-identical results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import apsw

from . import cache as _cache

log = logging.getLogger("vault-indexer.hybrid")


@dataclass(frozen=True)
class HybridConfig:
    alpha: float = 0.6
    beta: float = 0.25
    gamma: float = 0.15
    min_edges: int = 10
    recency_boost_days: int = 30
    recency_boost_amount: float = 0.05


def _months_since(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    delta = datetime.now(tz=timezone.utc) - ts
    return delta.days / 30.4375  # avg month length


def _is_recent(iso_ts: str | None, days_window: int) -> bool:
    if not iso_ts:
        return False
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    delta = datetime.now(tz=timezone.utc) - ts
    return 0 <= delta.days <= days_window


def _fetch_graph_scores(
    con: apsw.Connection, paths: list[str],
) -> dict[str, dict]:
    """Batch-fetch graph scores + recency basis for the result paths.

    Returns ``{path: {citation_rank, centrality, published_at, ingested_at}}``.
    Missing rows simply don't appear in the dict; callers treat absent as NULL.
    """
    if not paths:
        return {}
    placeholders = ",".join(["?"] * len(paths))
    out: dict[str, dict] = {}
    for row in con.execute(
        f"""
        SELECT path, citation_rank, centrality, published_at, ingested_at
        FROM vault_node
        WHERE path IN ({placeholders})
        """,
        paths,
    ):
        out[row[0]] = {
            "citation_rank": row[1],
            "centrality": row[2],
            "published_at": row[3],
            "ingested_at": row[4],
        }
    return out


def rerank(
    results: list[dict],
    con: apsw.Connection,
    cfg: HybridConfig,
) -> list[dict]:
    """Re-rank ``results`` using hybrid formula. Below the min_edges floor,
    return the input unchanged (no `hybrid_score` field).

    Mutates each result dict in place to add the `hybrid_score` field, then
    returns the list re-sorted by `hybrid_score` (descending).
    """
    if not results:
        return results

    total_edges = _cache.total_edge_count(con)
    if total_edges < cfg.min_edges:
        return results

    paths = [r["path"] for r in results if "path" in r]
    scores = _fetch_graph_scores(con, paths)

    for r in results:
        base = float(r.get("score", 0.0))
        meta = scores.get(r.get("path"), {})
        cr = meta.get("citation_rank")
        ce = meta.get("centrality")

        # Graceful degradation: fold missing-signal weights back into α.
        alpha_eff = cfg.alpha
        beta_eff = cfg.beta if cr is not None else 0.0
        gamma_eff = cfg.gamma if ce is not None else 0.0
        if cr is None:
            alpha_eff += cfg.beta
        if ce is None:
            alpha_eff += cfg.gamma

        recency_basis = meta.get("published_at") or meta.get("ingested_at")
        recency = (
            cfg.recency_boost_amount
            if _is_recent(recency_basis, cfg.recency_boost_days)
            else 0.0
        )

        hybrid = (
            alpha_eff * base
            + beta_eff * (cr or 0.0)
            + gamma_eff * (ce or 0.0)
            + recency
        )
        r["hybrid_score"] = hybrid

    results.sort(key=lambda x: x.get("hybrid_score", x.get("score", 0.0)), reverse=True)
    return results


def from_config() -> HybridConfig:
    """Build a HybridConfig from the global CONFIG. Convenience helper."""
    from .config import CONFIG
    return HybridConfig(
        alpha=CONFIG.graph_alpha,
        beta=CONFIG.graph_beta,
        gamma=CONFIG.graph_gamma,
        min_edges=CONFIG.graph_min_edges,
        recency_boost_days=CONFIG.recency_boost_days,
        recency_boost_amount=CONFIG.recency_boost_amount,
    )
