"""Graph compute job — PageRank, eigenvector centrality, Louvain clustering.

Loads edges from ``vault_edge`` into NetworkX graphs, runs the three
algorithms, and writes per-document scores back to ``vault_node``
(``citation_rank``, ``centrality``, ``cluster_id``).

Why three separate graphs:
- **Directed citation graph** (PageRank input) — only ``kind='citation'``.
  Captures "this hub note cites this source." Authority flows from many
  hub notes citing one source.
- **Undirected similarity graph** (eigenvector centrality + Louvain input) —
  ``kind IN ('citation', 'wikilink')`` treated as undirected. ``citation``
  edges count as cross-references. ``wikilink`` rows are operator-approved
  similarity edges from the review queue.
- **Excluded from both:** ``parent`` (folder hierarchy, not knowledge
  structure) and ``similarity_temporal`` (same-base-slug daily files,
  excluded to prevent multi-date thesis from inflating authority).

Determinism: PageRank converges; Louvain is randomized — passes ``seed=42``
to keep cluster IDs reproducible across runs (cluster IDs may still shift
when topology changes, but identical inputs produce identical outputs).

Concurrency: writes scores under one short transaction. WAL mode lets
``/search`` readers proceed during the long compute window.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

from . import cache as _cache
from .config import CONFIG

log = logging.getLogger("vault-indexer.graph_compute")

# Edge kinds that contribute to each graph.
_PAGERANK_KINDS: frozenset[str] = frozenset({"citation"})
_CENTRALITY_KINDS: frozenset[str] = frozenset({"citation", "wikilink"})


def _ms() -> float:
    return time.perf_counter() * 1000.0


def recompute(con, *, alpha: float = 0.85, seed: int = 42) -> dict:
    """Recompute graph scores for the connection's domain.

    Returns a stats dict (always — even on no-op/skip). On failure, returns
    a dict with ``status='error'``; never raises into the caller (the reload
    pipeline must remain robust).

    The graceful-degradation floor (``CONFIG.graph_min_edges``) is checked
    on the *centrality input* edge count. Below it: no-op, scores left as-is
    (already NULL in fresh vaults; left unchanged in once-populated graphs
    so a temporary dip in approvals doesn't wipe authority overnight).
    """
    if not _NX_AVAILABLE:
        log.warning("networkx not installed; skipping recompute")
        return {"status": "skipped_no_networkx"}

    t0 = _ms()
    edges_pagerank: list[tuple[str, str, float]] = []
    edges_centrality: list[tuple[str, str, float]] = []
    for src, dst, kind, weight in con.execute(
        "SELECT src_path, dst_path, kind, weight FROM vault_edge"
    ):
        if kind in _PAGERANK_KINDS:
            edges_pagerank.append((src, dst, float(weight)))
        if kind in _CENTRALITY_KINDS:
            edges_centrality.append((src, dst, float(weight)))

    if len(edges_centrality) < CONFIG.graph_min_edges:
        stats = {
            "status": "below_floor",
            "centrality_edges": len(edges_centrality),
            "pagerank_edges": len(edges_pagerank),
            "min_edges_floor": CONFIG.graph_min_edges,
            "total_ms": round(_ms() - t0, 2),
        }
        log.info("recompute %s", stats)
        return stats

    # Build directed graph for PageRank.
    DG = nx.DiGraph()
    for src, dst, w in edges_pagerank:
        DG.add_edge(src, dst, weight=w)
    # Build undirected graph for eigenvector + Louvain.
    UG = nx.Graph()
    for src, dst, w in edges_centrality:
        if UG.has_edge(src, dst):
            UG[src][dst]["weight"] += w
        else:
            UG.add_edge(src, dst, weight=w)

    # PageRank.
    t = _ms()
    if DG.number_of_edges() == 0:
        pagerank: dict[str, float] = {}
        pr_iters: Optional[int] = None
    else:
        pagerank = nx.pagerank(DG, alpha=alpha, max_iter=200, tol=1e-6, weight="weight")
        pr_iters = None  # nx.pagerank doesn't expose iteration count
    pagerank_ms = round(_ms() - t, 2)

    # Eigenvector centrality. Falls back to a trivial value if the graph is
    # disconnected or convergence fails.
    t = _ms()
    centrality: dict[str, float] = {}
    if UG.number_of_edges() > 0:
        try:
            centrality = nx.eigenvector_centrality(
                UG, max_iter=1000, tol=1e-6, weight="weight",
            )
        except (nx.PowerIterationFailedConvergence, nx.NetworkXException) as e:
            log.warning("eigenvector centrality failed (%s); using degree-centrality fallback", e)
            centrality = nx.degree_centrality(UG)
    centrality_ms = round(_ms() - t, 2)

    # Louvain communities.
    t = _ms()
    cluster_id_for: dict[str, int] = {}
    cluster_count = 0
    if UG.number_of_nodes() > 0:
        communities = nx.community.louvain_communities(
            UG, seed=seed, weight="weight",
        )
        cluster_count = len(communities)
        for cid, members in enumerate(communities):
            for node in members:
                cluster_id_for[node] = cid
    louvain_ms = round(_ms() - t, 2)

    # Atomic write-back. Touch only nodes that appeared in any graph; leave
    # disconnected nodes with their previous (or NULL) scores untouched.
    paths_touched = set(pagerank) | set(centrality) | set(cluster_id_for)
    rows = [
        (
            pagerank.get(p),
            centrality.get(p),
            cluster_id_for.get(p),
            p,
        )
        for p in paths_touched
    ]
    write_t = _ms()
    if rows:
        with _cache.transaction(con) as cur:
            cur.executemany(
                """
                UPDATE vault_node
                SET citation_rank = ?, centrality = ?, cluster_id = ?
                WHERE path = ?
                """,
                rows,
            )
    write_ms = round(_ms() - write_t, 2)

    # Detect new clusters (≥3 nodes that weren't grouped together previously).
    # Append concept slugs to Topics/<domain>/_concepts_to_draft.md.
    new_concepts: list[str] = []
    if cluster_id_for and CONFIG.domain:
        try:
            new_concepts = _detect_and_queue_new_clusters(
                con=con,
                cluster_id_for=cluster_id_for,
                pagerank=pagerank,
                centrality=centrality,
            )
        except Exception as e:                                # noqa: BLE001
            log.exception("cluster change detection failed: %s", e)

    stats = {
        "status": "ok",
        "domain": CONFIG.domain,
        "nodes_pagerank": DG.number_of_nodes(),
        "edges_pagerank": DG.number_of_edges(),
        "nodes_centrality": UG.number_of_nodes(),
        "edges_centrality": UG.number_of_edges(),
        "clusters": cluster_count,
        "new_concepts_queued": len(new_concepts),
        "rows_updated": len(rows),
        "pagerank_ms": pagerank_ms,
        "centrality_ms": centrality_ms,
        "louvain_ms": louvain_ms,
        "write_ms": write_ms,
        "total_ms": round(_ms() - t0, 2),
    }
    log.info("recompute %s", stats)
    return stats


# ---------- Health summary + cluster change detection ----------

def health_summary(con) -> dict:
    """Snapshot of the current graph state for the review queue.

    Cheap (a few aggregates + a top-N query). Read-only.
    """
    edge_counts = _cache.edge_counts_by_kind(con)
    node_count = list(con.execute("SELECT COUNT(*) FROM vault_node"))[0][0]
    scored_count = list(con.execute(
        "SELECT COUNT(*) FROM vault_node WHERE citation_rank IS NOT NULL"
    ))[0][0]
    cluster_count = list(con.execute(
        "SELECT COUNT(DISTINCT cluster_id) FROM vault_node WHERE cluster_id IS NOT NULL"
    ))[0][0]
    top_cited = [
        (r[0], r[1])
        for r in con.execute(
            """
            SELECT path, citation_rank FROM vault_node
            WHERE citation_rank IS NOT NULL
            ORDER BY citation_rank DESC LIMIT 5
            """
        )
    ]
    top_central = [
        (r[0], r[1])
        for r in con.execute(
            """
            SELECT path, centrality FROM vault_node
            WHERE centrality IS NOT NULL
            ORDER BY centrality DESC LIMIT 5
            """
        )
    ]
    return {
        "node_count": int(node_count),
        "scored_count": int(scored_count),
        "edge_counts": edge_counts,
        "total_edges": sum(edge_counts.values()),
        "cluster_count": int(cluster_count),
        "top_cited": top_cited,
        "top_central": top_central,
        "recompute_floor": CONFIG.graph_min_edges,
    }


_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Reps from these node kinds are not meaningful concept names — they're
# navigational scaffolding. Skip them when picking a cluster representative.
_NAVIGATIONAL_KINDS: frozenset[str] = frozenset({"folder_context"})

# Reps whose filename stem (case-insensitive) is one of these are navigational
# index files even if the indexer didn't tag them as folder_context.
_NAVIGATIONAL_STEMS: frozenset[str] = frozenset({
    "index", "_index", "readme", "_readme", "welcome", "_welcome",
})


def _slugify_title(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:80]


def _shorten_title(title: str) -> str:
    """Strip common book/series prefixes before slugifying for concept queue.

    Vault titles follow conventions like:
        "The Intelligent Investor — Margin of Safety as the Central Concept"
        "Stress-test: aapl-wedge-with-ctx"
    The rightmost segment after `" — "` or `": "` is the specific
    chapter/topic title — that's what we want as a concept candidate.
    """
    for sep in (" — ", " - ", ": "):
        if sep in title:
            return title.rsplit(sep, 1)[-1].strip()
    return title.strip()


def _is_navigational_rep(
    path: str, node_meta: dict[str, tuple[str | None, str | None]]
) -> bool:
    """True if ``path`` is a navigational/index file unsuitable as a concept rep."""
    kind, _title = node_meta.get(path, (None, None))
    if kind in _NAVIGATIONAL_KINDS:
        return True
    stem = Path(path).stem.lower()
    return stem in _NAVIGATIONAL_STEMS


def _cluster_state_path() -> Path:
    return CONFIG.db_path.parent / f"cluster_state_{CONFIG.domain}.json"


def _concepts_file_path() -> Path:
    return CONFIG.vault_path / "Topics" / (CONFIG.domain or "") / "_concepts_to_draft.md"


def _detect_and_queue_new_clusters(
    *,
    con,
    cluster_id_for: dict[str, int],
    pagerank: dict[str, float],
    centrality: dict[str, float],
) -> list[str]:
    """Diff this run's clusters vs prior run's; for each NEW cluster (≥3 nodes
    that weren't grouped together before), append a candidate concept slug to
    `Topics/<domain>/_concepts_to_draft.md`.

    The slug is derived from the highest-centrality non-navigational member's
    ``vault_node.title`` (falling back to filename stem if title is empty).
    Navigational reps (``kind='folder_context'`` or stems like ``index`` /
    ``_index`` / ``readme``) are skipped — they're scaffolding, not concepts.

    State file: ``<db_dir>/cluster_state_<domain>.json``. Stores last run's
    cluster membership for diffing.
    """
    state_path = _cluster_state_path()
    prev: dict[str, list[str]] = {}
    if state_path.exists():
        try:
            prev = json.loads(state_path.read_text(encoding="utf-8")).get("clusters", {})
        except Exception:                                     # noqa: BLE001
            prev = {}

    # Group this run's clusters → set of member paths.
    by_cluster: dict[int, list[str]] = {}
    for path, cid in cluster_id_for.items():
        by_cluster.setdefault(cid, []).append(path)

    # Batch-fetch (kind, title) for every clustered path — one query, in-memory
    # lookups during rep selection.
    all_paths = list({p for members in by_cluster.values() for p in members})
    node_meta: dict[str, tuple[str | None, str | None]] = {}
    if all_paths:
        placeholders = ",".join(["?"] * len(all_paths))
        for row in con.execute(
            f"SELECT path, kind, title FROM vault_node WHERE path IN ({placeholders})",
            all_paths,
        ):
            node_meta[row[0]] = (row[1], row[2])

    # A "new" cluster (semantically) = a set of members that wasn't together
    # in any previous cluster. We compare frozenset membership.
    prev_member_sets = [frozenset(members) for members in prev.values()]
    new_concepts: list[str] = []
    for members in by_cluster.values():
        if len(members) < 3:
            continue
        member_set = frozenset(members)
        if any(member_set <= prev_set for prev_set in prev_member_sets):
            continue                # subset of an already-known cluster
        # Rank members by (centrality, pagerank) desc, then pick the first
        # non-navigational one. Falls through to None if every member is
        # navigational — in which case we skip this cluster (no concept
        # candidate worth surfacing).
        ranked = sorted(
            members,
            key=lambda p: (centrality.get(p, 0.0), pagerank.get(p, 0.0)),
            reverse=True,
        )
        rep: str | None = next(
            (p for p in ranked if not _is_navigational_rep(p, node_meta)),
            None,
        )
        if rep is None:
            continue
        # Prefer the human-readable title (stripped of book/series prefix);
        # fall back to filename stem only when title is empty/missing.
        _kind, title = node_meta.get(rep, (None, None))
        source = (
            _shorten_title(title)
            if title and title.strip()
            else Path(rep).stem
        )
        slug = _slugify_title(source)
        if slug and slug not in _NAVIGATIONAL_STEMS:
            new_concepts.append(slug)

    # Append new concepts to the queue file (idempotent).
    if new_concepts:
        _append_to_concepts_queue(new_concepts)

    # Persist this run's clusters for next-run diffing.
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "run_at": datetime.now(tz=timezone.utc).isoformat(),
                "clusters": {str(cid): members for cid, members in by_cluster.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return new_concepts


def _append_to_concepts_queue(slugs: list[str]) -> None:
    """Idempotently append slugs to the `## Queue` section of
    `Topics/<domain>/_concepts_to_draft.md`. Replaces the section in place
    so multiple runs don't create multiple `## Queue` headers.
    """
    target = _concepts_file_path()
    if not target.parent.exists():
        log.warning("concepts queue dir missing: %s", target.parent)
        return
    existing = target.read_text(encoding="utf-8") if target.exists() else "## Queue\n\n## Done\n"

    # Parse existing queue items (case-insensitive on the slug).
    existing_slugs: set[str] = set()
    in_queue = False
    for line in existing.splitlines():
        s = line.strip()
        if s.lower() == "## queue":
            in_queue = True
            continue
        if s.startswith("## ") and in_queue:
            in_queue = False
            continue
        if in_queue and s.startswith("- [ ]"):
            existing_slugs.add(_slugify_title(s[5:].strip()))
        if in_queue and s.startswith("- [x]"):
            existing_slugs.add(_slugify_title(s[5:].strip()))

    additions = [s for s in slugs if s not in existing_slugs]
    if not additions:
        return

    # Insert additions at the end of the `## Queue` block (before next `## ` heading).
    lines = existing.splitlines()
    out_lines: list[str] = []
    inserted = False
    in_queue = False
    for line in lines:
        s = line.strip()
        if s.lower() == "## queue":
            in_queue = True
            out_lines.append(line)
            continue
        if in_queue and s.startswith("## ") and s.lower() != "## queue":
            # End of queue block — flush additions before this heading.
            for slug in additions:
                out_lines.append(f"- [ ] {slug}")
            inserted = True
            in_queue = False
        out_lines.append(line)
    if not inserted:
        # Queue had no following section — append at end.
        for slug in additions:
            out_lines.append(f"- [ ] {slug}")
    target.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    log.info("queued %d new concept candidates → %s", len(additions), target.name)
