"""Wikilink → citation edge extractor.

Runs at chunk-write time inside ``indexer.index_one()``. For each `.md` body,
extracts every ``[[wikilink]]``, resolves via the alias map, looks up the
canonical vault path, and returns a list of edge tuples to insert into
``vault_edge``.

Edge kinds emitted:

- ``citation`` — directed (src cites dst). Default classification.
- ``similarity_temporal`` — same base slug + multi-date prefix
  (e.g. ``2026-05-04-aapl-wedge-skip.md`` ↔ ``2026-05-07-aapl-wedge-skip.md``).
  Excluded from PageRank / centrality at recompute time so daily research
  files don't inflate authority for the underlying ticker.

Path resolution strategy (in order):

1. Treat as full vault-relative path; check ``vault_node`` for exact match.
2. Append ``.md`` suffix and re-check.
3. Slug-only fallback: query ``vault_node`` for any path whose basename
   (with or without ``.md``) matches the slug. If multiple, pick
   lexicographically-first (deterministic; warn).

Cross-domain validation is intentionally **not** performed — each sidecar
owns a physically separate DB, so cross-domain links cannot be inserted
even if the wikilink syntactically points at another domain's path
(the lookup just returns no row, treated as a dead link).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import apsw

from .aliases import resolve

log = logging.getLogger("vault-indexer.citations")

# Matches [[Target]] or [[Target|Display text]]; captures Target.
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Same base slug, different YYYY-MM-DD or YYYY-Www date prefix.
_DATE_PREFIX = re.compile(r"^(?:\d{4}-\d{2}-\d{2}-|\d{4}-w\d{2}-)(.+)$", re.IGNORECASE)

# Kinds owned by the indexer (managed by replace_edges_by_kinds when a body
# is re-indexed). 'wikilink' is owned by the review queue and intentionally
# preserved across re-indexing.
INDEXER_OWNED_KINDS: tuple[str, ...] = (
    "parent",
    "citation",
    "similarity_temporal",
)


def _strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block if present."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def _base_slug(filename: str) -> str | None:
    """Return the part after a date prefix, or None if no date prefix."""
    stem = Path(filename).stem
    m = _DATE_PREFIX.match(stem)
    return m.group(1) if m else None


def _is_temporal_pair(src_path: str, dst_path: str) -> bool:
    """True if both paths share a base slug under different date prefixes."""
    sb = _base_slug(Path(src_path).name)
    db = _base_slug(Path(dst_path).name)
    return bool(sb and db and sb == db and src_path != dst_path)


def _resolve_target(
    raw_target: str,
    alias_map: dict[str, str],
    src_path: str,
    con: apsw.Connection,
) -> str | None:
    """Look up the canonical vault path for a wikilink target.

    Returns the resolved ``vault_node.path`` or ``None`` if no candidate
    exists in this domain's index (treat as dead link).
    """
    canonical = resolve(raw_target, alias_map)

    # 1. Try as a full path (with and without .md suffix).
    candidates = [canonical, canonical if canonical.endswith(".md") else canonical + ".md"]
    for cand in candidates:
        row = con.execute(
            "SELECT path FROM vault_node WHERE path = ? LIMIT 1", (cand,),
        ).fetchone()
        if row:
            return row[0]

    # 2. Slug-only fallback: any path whose basename (sans .md) matches.
    slug = Path(canonical).stem
    rows = con.execute(
        "SELECT path FROM vault_node WHERE path LIKE ? OR path LIKE ?",
        (f"%/{slug}.md", f"{slug}.md"),
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        chosen = min(r[0] for r in rows)
        log.warning(
            "wikilink %r in %s matched %d files; chose %r (lex-first). "
            "Add an alias to disambiguate.",
            raw_target, src_path, len(rows), chosen,
        )
        return chosen
    return rows[0][0]


def parse_citations(
    body_md: str,
    src_path: str,
    *,
    alias_map: dict[str, str],
    con: apsw.Connection,
) -> tuple[list[tuple[str, str, float]], list[str]]:
    """Extract citation/temporal edges from one document body.

    Returns ``(edges, dead_targets)`` where:
      - ``edges`` is a list of ``(dst_path, kind, weight)`` tuples — the
        same shape ``cache.replace_edges`` expects, plus ``kind``.
      - ``dead_targets`` is a list of raw wikilink strings that did not
        resolve in this domain (used by the dead-link reporter).

    Self-references (``src == dst``) are dropped.
    Duplicate edges to the same dst with the same kind are deduped; the
    PRIMARY KEY on (src, dst, kind) would catch them anyway, but caller
    code expects no duplicate-INSERT-OR-REPLACE churn.
    """
    body = _strip_frontmatter(body_md)
    edges: list[tuple[str, str, float]] = []
    dead: list[str] = []
    seen: set[tuple[str, str]] = set()  # (dst, kind) dedupe

    for m in _WIKILINK.finditer(body):
        raw_target = m.group(1).strip()
        if not raw_target:
            continue
        dst = _resolve_target(raw_target, alias_map, src_path, con)
        if dst is None:
            dead.append(raw_target)
            continue
        if dst == src_path:
            continue
        kind = "similarity_temporal" if _is_temporal_pair(src_path, dst) else "citation"
        key = (dst, kind)
        if key in seen:
            continue
        seen.add(key)
        edges.append((dst, kind, 1.0))
    return edges, dead


def collect_observed_targets(
    body_md: str,
    *,
    alias_map: dict[str, str],
) -> set[str]:
    """Return the set of slugified wikilink targets observed in a body.

    Used by ``aliases.suggest_conflicts`` over a corpus to surface
    edit-distance duplicates.
    """
    body = _strip_frontmatter(body_md)
    out: set[str] = set()
    for m in _WIKILINK.finditer(body):
        raw = m.group(1).strip()
        if raw:
            out.add(resolve(raw, alias_map))
    return out
