"""One-shot citation backfill.

Walks every row in ``vault_node`` and runs ``citations.parse_citations`` on
its body, writing the resulting edges via ``cache.replace_edges_by_kinds``.

Why this script exists separately from ``indexer.index_one``: that hook only
fires when ``body_hash`` changes. After Phase 1 ships the indexer change,
existing files with unchanged bodies still need their citations extracted
once. After backfill the indexer hook handles incremental updates forever.

Idempotent: replace_edges_by_kinds deletes only the indexer-owned kinds
(parent, citation, similarity_temporal) before re-inserting, so re-running
the backfill produces the same final state. ``wikilink`` rows survive.

Usage::

    DOMAIN=finance python -m tools.vault_indexer.backfill_citations
    DOMAIN=fitness python -m tools.vault_indexer.backfill_citations --dry-run

Without DOMAIN env it falls back to CONFIG defaults (single-vault legacy).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import aliases as _aliases
from . import cache as _cache
from . import citations as _citations
from .config import CONFIG

log = logging.getLogger("vault-indexer.backfill")


def backfill(*, dry_run: bool = False, max_conflict_suggestions: int = 20) -> dict:
    """Run citation backfill against ``CONFIG.db_path``.

    Returns a stats dict suitable for printing or piping to the review queue
    later.
    """
    log.info(
        "backfill start: domain=%s vault=%s db=%s dry_run=%s",
        CONFIG.domain, CONFIG.vault_path, CONFIG.db_path, dry_run,
    )
    con = _cache.init(CONFIG.db_path, CONFIG.embedding_dim)
    alias_map = _aliases.load_alias_map(CONFIG.vault_path, CONFIG.domain)

    rows = list(con.execute("SELECT path, body_md, kind FROM vault_node"))
    stats = {
        "files_scanned": len(rows),
        "files_with_wikilinks": 0,
        "citation_edges": 0,
        "temporal_edges": 0,
        "dead_targets": 0,
        "files_updated": 0,
        "alias_conflict_candidates": 0,
    }
    dead_log: list[tuple[str, str]] = []
    observed_targets: set[str] = set()

    for path, body, kind in rows:
        if kind == "folder_context" or not body:
            continue
        observed_targets |= _citations.collect_observed_targets(
            body, alias_map=alias_map,
        )
        edges, dead = _citations.parse_citations(
            body, path, alias_map=alias_map, con=con,
        )
        if not edges and not dead:
            continue
        stats["files_with_wikilinks"] += 1
        for d in dead:
            dead_log.append((path, d))
        stats["dead_targets"] += len(dead)

        # Build the edge batch for this src. We still need to write the parent
        # edge (if any) since replace_edges_by_kinds will wipe it before insert.
        node_row = con.execute(
            "SELECT parent_path FROM vault_node WHERE path = ? LIMIT 1", (path,),
        ).fetchone()
        parent_path = node_row[0] if node_row else None
        new_edges: list[tuple[str, str, float]] = []
        if parent_path:
            new_edges.append((parent_path, "parent", 1.0))
        for dst, ekind, w in edges:
            new_edges.append((dst, ekind, w))
            if ekind == "citation":
                stats["citation_edges"] += 1
            elif ekind == "similarity_temporal":
                stats["temporal_edges"] += 1
        if dry_run:
            continue
        with _cache.transaction(con) as cur:
            _cache.replace_edges_by_kinds(
                cur, path, _citations.INDEXER_OWNED_KINDS, new_edges,
            )
        stats["files_updated"] += 1

    suggestions = _aliases.suggest_conflicts(
        observed_targets, alias_map,
        max_suggestions=max_conflict_suggestions,
    )
    stats["alias_conflict_candidates"] = len(suggestions)

    log.info("backfill done: %s", stats)
    if dead_log[:10]:
        log.info("first 10 dead targets:")
        for src, target in dead_log[:10]:
            log.info("  %s -> %r", src, target)
    if suggestions[:10]:
        log.info("first 10 alias conflict candidates (consider adding to _aliases-%s.md):", CONFIG.domain)
        for a, b, ratio in suggestions[:10]:
            log.info("  %s ↔ %s (ratio=%.2f)", a, b, ratio)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and report; do not write to DB.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-file logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    stats = backfill(dry_run=args.dry_run)
    print()
    print("=== BACKFILL SUMMARY ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
