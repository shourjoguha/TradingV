"""Discover dead wikilinks across the indexed corpus.

A dead link = a ``[[wikilink]]`` whose target does not resolve to any node
in this domain's index. Surfaced in the review queue so the operator can
either fix the source's wikilink text or remove the broken reference.

This module re-walks ``vault_node`` bodies on demand. The same logic runs
inline during ``indexer.index_one()`` per file (cheap), but only that one
file's dead links are visible there. ``discover_all()`` aggregates across
the whole corpus for the review queue.
"""
from __future__ import annotations

import logging

from . import aliases as _aliases
from . import citations as _citations
from .config import CONFIG

log = logging.getLogger("vault-indexer.dead_links")


def discover_all(con) -> list[tuple[str, str]]:
    """Return ``[(source_path, raw_target_text), ...]`` for every dead link
    currently observable in the index. Sorted by source path for stable diffs.
    """
    alias_map = _aliases.load_alias_map(CONFIG.vault_path, CONFIG.domain)
    dead: list[tuple[str, str]] = []
    for path, body, kind in con.execute(
        "SELECT path, body_md, kind FROM vault_node"
    ):
        if kind == "folder_context" or not body:
            continue
        _edges, dead_targets = _citations.parse_citations(
            body, path, alias_map=alias_map, con=con,
        )
        for target in dead_targets:
            dead.append((path, target))
    dead.sort()
    return dead


def discover_observed_targets(con) -> set[str]:
    """All resolved-via-alias slugified wikilink targets in the corpus.

    Used to feed ``aliases.suggest_conflicts`` for the review queue.
    """
    alias_map = _aliases.load_alias_map(CONFIG.vault_path, CONFIG.domain)
    observed: set[str] = set()
    for path, body, kind in con.execute(
        "SELECT path, body_md, kind FROM vault_node"
    ):
        if kind == "folder_context" or not body:
            continue
        observed |= _citations.collect_observed_targets(body, alias_map=alias_map)
    return observed
