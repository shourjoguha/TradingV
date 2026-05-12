"""Review queue — `_review-queue.md` round-trip.

Indexer writes pending suggestions as Obsidian checkboxes. Operator ticks
boxes in their editor. On the next indexer sweep, ticks are read back,
applied to the vault (frontmatter tag updates, edge promotions, etc.),
and the queue is rewritten with the next batch.

Markdown is the wire format. There is no separate review DB.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cache as _cache
from . import indexer as _indexer
from . import search as _search
from .config import CONFIG
from .vault import parse_file


REVIEW_FILE = CONFIG.review_file

# `- [ ] tag: name` / `- [x] tag: name` / `- [ ] link → other.md (sim 0.8)` etc.
_CHECKBOX = re.compile(r"^\s*- \[(?P<state>[ xX])\] (?P<rest>.*)$")
_TAG_RE = re.compile(r"tag:\s*`?(?P<tag>[a-z0-9_]+)`?")
_LINK_RE = re.compile(r"link\s*(?:→|->)\s*(?P<dst>[^\s(]+)")
_DRAFT_RE = re.compile(r"promote draft:\s*`?(?P<path>[^`\s]+\.md\.draft)`?")


@dataclass
class ReviewQueue:
    sections: list[tuple[str, list[str]]] = field(default_factory=list)


def render(suggestions: dict) -> str:
    """Render the suggestions dict as a markdown review queue."""
    today = datetime.date.today().isoformat()
    lines = [
        f"# Review queue — generated {today}",
        "",
        "Tick boxes in Obsidian, save, and the indexer will apply them on the next watch event.",
        "",
    ]

    auto_tags = suggestions.get("auto_tags") or {}
    if auto_tags:
        lines.append("## Auto-tag suggestions")
        lines.append("")
        for path, tags in sorted(auto_tags.items()):
            lines.append(f"### {path}")
            for t in tags:
                lines.append(f"- [ ] tag: `{t}`")
            lines.append("")

    cross_links = suggestions.get("cross_links") or {}
    if cross_links:
        lines.append("## Cross-link suggestions (similarity > 0.78)")
        lines.append("")
        for path, neighbours in sorted(cross_links.items()):
            lines.append(f"### {path}")
            for npath, sim in neighbours:
                lines.append(f"- [ ] link → {npath} (sim {sim:.2f})")
            lines.append("")

    orphans = suggestions.get("orphan_tags") or []
    if orphans:
        lines.append("## Orphaned tags (in notes but no longer in vocabulary)")
        lines.append("")
        for tag, count in orphans:
            lines.append(f"- `{tag}` — used in {count} note(s). Re-tag manually or accept as deprecated.")
        lines.append("")

    pending_drafts = suggestions.get("pending_drafts") or []
    if pending_drafts:
        lines.append("## Pending video drafts (auto-ingested; promote to canonical)")
        lines.append("")
        for d in pending_drafts:
            path = d["path"]
            title = str(d.get("title") or path)
            author = str(d.get("author") or "")
            published = str(d.get("published_at") or "")
            byline = " · ".join(p for p in (author, published) if p)
            lines.append(f"### {path}")
            lines.append(f"- {title}" + (f"  *({byline})*" if byline else ""))
            lines.append(f"- [ ] promote draft: `{path}`")
            lines.append("")

    rename_log = suggestions.get("rename_log") or []
    if rename_log:
        lines.append("## Renames applied")
        lines.append("")
        for old, new, count in rename_log:
            lines.append(f"- `{old}` → `{new}` (rewrote {count} note(s))")
        lines.append("")

    dead_links = suggestions.get("dead_links") or []
    if dead_links:
        lines.append(f"## Dead links (detected {today})")
        lines.append("")
        lines.append("Each row: `source.md → 'raw target text'`. Either fix the wikilink or remove it; targets that resolve again automatically disappear from this section on next reload.")
        lines.append("")
        for src, target in dead_links:
            lines.append(f"- `{src}` → `{target}`")
        lines.append("")

    alias_conflicts = suggestions.get("alias_conflicts") or []
    if alias_conflicts:
        lines.append("## Possible alias conflicts")
        lines.append("")
        lines.append("Pairs of wikilink targets that look like duplicates. If they are the same concept, add an entry to `_aliases-<domain>.md`. If genuinely distinct, ignore.")
        lines.append("")
        for a, b, ratio in alias_conflicts:
            lines.append(f"- `{a}` ↔ `{b}`  *(similarity {ratio:.2f})*")
        lines.append("")

    health = suggestions.get("graph_health")
    if health:
        lines.append("## Graph health")
        lines.append("")
        lines.append(f"- Nodes indexed: **{health['node_count']}**, scored: **{health['scored_count']}**, clusters: **{health['cluster_count']}**")
        lines.append(f"- Edges: total **{health['total_edges']}** (floor for hybrid: {health['recompute_floor']})")
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(health['edge_counts'].items())) or "—"
        lines.append(f"  - by kind: {kinds}")
        if health.get("top_cited"):
            lines.append("- Most-cited (PageRank):")
            for path, score in health["top_cited"]:
                lines.append(f"  - `{path}` — {score:.4f}")
        if health.get("top_central"):
            lines.append("- Most central (eigenvector):")
            for path, score in health["top_central"]:
                lines.append(f"  - `{path}` — {score:.4f}")
        lines.append("")

    if not (auto_tags or cross_links or orphans or rename_log or pending_drafts or dead_links or alias_conflicts):
        lines.append("Nothing pending. Indexer will repopulate as new content arrives.")
        lines.append("")

    return "\n".join(lines)


def write(vault_root: Path, content: str) -> None:
    target = vault_root / REVIEW_FILE
    target.write_text(content, encoding="utf-8")


def read(vault_root: Path) -> str:
    target = vault_root / REVIEW_FILE
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


def parse_ticks(text: str) -> list[tuple[str, dict]]:
    """Return list of (action_kind, payload) for each ticked checkbox.

    action_kind ∈ {'tag', 'link'}; payload depends on kind.
    Tracks which markdown section ("### path/foo.md") each tick belongs to,
    so promote() knows which note to mutate.
    """
    out: list[tuple[str, dict]] = []
    current_path: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("### "):
            current_path = s[4:].strip()
            continue
        m = _CHECKBOX.match(line)
        if not m:
            continue
        if m.group("state") not in ("x", "X"):
            continue
        rest = m.group("rest")
        # Draft-promote ticks carry their own absolute-in-vault path, so they
        # don't depend on the surrounding `### path` header.
        draft_m = _DRAFT_RE.search(rest)
        if draft_m:
            out.append(("draft_promote", {"path": draft_m.group("path")}))
            continue
        if current_path is None:
            continue
        tag_m = _TAG_RE.search(rest)
        if tag_m:
            out.append(("tag", {"path": current_path, "tag": tag_m.group("tag")}))
            continue
        link_m = _LINK_RE.search(rest)
        if link_m:
            out.append(("link", {"src": current_path, "dst": link_m.group("dst").rstrip(".,)")}))
    return out


def promote(con, vault_root: Path, ticks: list[tuple[str, dict]]) -> dict:
    """Apply ticked actions to the vault.

    For 'tag': append tag to the note's frontmatter (idempotent).
    For 'link': insert an explicit edge into vault_edge with kind='wikilink'.
    For 'draft_promote': rename `<x>.md.draft` → `<x>.md`, strip `draft: true`.
    """
    from . import citations as _citations
    counts = {
        "tags_added": 0, "links_added": 0,
        "temporal_links_demoted": 0,
        "skipped": 0, "drafts_promoted": 0,
    }
    by_path: dict[str, list[str]] = {}
    edges: list[tuple[str, str, str, float]] = []
    drafts: list[str] = []
    for kind, payload in ticks:
        if kind == "tag":
            by_path.setdefault(payload["path"], []).append(payload["tag"])
        elif kind == "link":
            # Defense-in-depth: even if a temporal pair slipped past the
            # suggestion filter, classify on insert so it lands in the right
            # bucket (excluded from PageRank/centrality at recompute).
            src, dst = payload["src"], payload["dst"]
            edge_kind = (
                "similarity_temporal"
                if _citations._is_temporal_pair(src, dst)
                else "wikilink"
            )
            if edge_kind == "similarity_temporal":
                counts["temporal_links_demoted"] += 1
            edges.append((src, dst, edge_kind, 1.0))
        elif kind == "draft_promote":
            drafts.append(payload["path"])

    for rel_path, new_tags in by_path.items():
        abs_path = vault_root / rel_path
        if not abs_path.exists():
            counts["skipped"] += len(new_tags)
            continue
        node = parse_file(abs_path, vault_root)
        merged = sorted(set(node.tags) | set(new_tags))
        _indexer.write_frontmatter(abs_path, tags=merged)
        counts["tags_added"] += len(set(new_tags) - set(node.tags))

    if edges:
        with _cache.transaction(con) as cur:
            for src, dst, kind, weight in edges:
                cur.execute(
                    "INSERT OR REPLACE INTO vault_edge (src_path, dst_path, kind, weight) VALUES (?, ?, ?, ?)",
                    (src, dst, kind, weight),
                )
                counts["links_added"] += 1

    for rel_path in drafts:
        if promote_draft_path(vault_root, rel_path):
            counts["drafts_promoted"] += 1
        else:
            counts["skipped"] += 1
    return counts


def promote_draft_path(vault_root: Path, rel_path: str) -> bool:
    """Promote a single ``<x>.md.draft`` to ``<x>.md``.

    Strips ``draft: true`` from frontmatter, then renames. Idempotent + safe:
    returns ``False`` (no-op) when the source is missing, the destination
    already exists, or the path doesn't end in ``.md.draft``. Returns
    ``True`` on a successful promote.

    Reused by both the review-queue ``promote()`` flow and the
    ``auto_promote`` post-step in ``youtube_channel.ingest_one()``.
    """
    if not rel_path.endswith(".md.draft"):
        return False
    src = vault_root / rel_path
    if not src.exists():
        return False
    dst_rel = rel_path[: -len(".draft")]                 # ...md.draft → ...md
    dst = vault_root / dst_rel
    if dst.exists():
        return False
    # Strip `draft: true` from frontmatter before rename.
    try:
        import frontmatter as _fm
        text = src.read_text(encoding="utf-8")
        post = _fm.loads(text)
        if "draft" in post.metadata:
            del post.metadata["draft"]
        src.write_text(_fm.dumps(post) + "\n", encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    src.rename(dst)
    return True


def gather_suggestions(
    con,
    *,
    vocabulary: dict[str, str],
    similarity_threshold: float = 0.78,
    cross_link_per_node: int = 3,
) -> dict:
    """Build the suggestions dict for a fresh review queue."""
    from . import aliases as _aliases
    from . import auto_tag as _auto
    from . import dead_links as _dead_links
    from . import graph_compute as _graph_compute

    auto_tags: dict[str, list[str]] = {}
    cross_links: dict[str, list[tuple[str, float]]] = {}
    orphan_count: dict[str, int] = {}

    nodes = list(con.execute(
        "SELECT path, title, body_md, tags FROM vault_node ORDER BY last_indexed_at DESC LIMIT 50"
    ))
    for path, title, body_md, tags_json in nodes:
        import json as _json
        existing_tags = set(_json.loads(tags_json))
        # Auto-tag only when no tags yet (avoid pestering on already-tagged notes).
        if not existing_tags and vocabulary:
            sug = _auto.suggest(title=title or "", body=body_md, vocabulary=vocabulary)
            if sug:
                auto_tags[path] = sug
        # Cross-link suggestions per-note. similar_to_node returns dicts.
        # Phase 6: filter out temporal-series pairs (same base slug, different
        # date prefix). Promoting these as `wikilink` would feed eigenvector
        # centrality with same-thesis daily snapshots and inflate authority
        # for the underlying ticker (e.g. AAPL daily files all linking each
        # other). They live in the index as `similarity_temporal` already.
        from . import citations as _citations
        raw_sims = _search.similar_to_node(con, path, k=cross_link_per_node * 2, exclude_self=True)
        sims = [
            (r["path"], r["similarity"])
            for r in raw_sims
            if r.get("similarity", 0.0) >= similarity_threshold
            and not _citations._is_temporal_pair(path, r["path"])
        ][:cross_link_per_node]
        if sims:
            cross_links[path] = sims
        # Orphan tags — tags on this note that aren't in vocabulary.
        for t in existing_tags:
            if t not in vocabulary:
                orphan_count[t] = orphan_count.get(t, 0) + 1

    orphans = sorted(orphan_count.items(), key=lambda kv: -kv[1])

    # Graph-layer additions (Phase 5). Each is best-effort — if the graph
    # layer hasn't computed yet, these come back empty and the queue degrades
    # gracefully back to its pre-graph shape.
    dead_links: list[tuple[str, str]] = []
    alias_conflicts: list[tuple[str, str, float]] = []
    graph_health: dict | None = None
    try:
        dead_links = _dead_links.discover_all(con)
    except Exception as e:                                # noqa: BLE001
        import logging
        logging.getLogger("vault-indexer.review").warning(
            "dead_links discovery failed: %s", e,
        )
    try:
        observed = _dead_links.discover_observed_targets(con)
        alias_map = _aliases.load_alias_map(CONFIG.vault_path, CONFIG.domain)
        alias_conflicts = _aliases.suggest_conflicts(observed, alias_map)
    except Exception as e:                                # noqa: BLE001
        import logging
        logging.getLogger("vault-indexer.review").warning(
            "alias conflict scan failed: %s", e,
        )
    try:
        graph_health = _graph_compute.health_summary(con)
    except Exception as e:                                # noqa: BLE001
        import logging
        logging.getLogger("vault-indexer.review").warning(
            "graph health summary failed: %s", e,
        )

    return {
        "auto_tags": auto_tags,
        "cross_links": cross_links,
        "orphan_tags": orphans,
        "pending_drafts": _scan_pending_drafts(CONFIG.vault_path),
        "dead_links": dead_links,
        "alias_conflicts": alias_conflicts,
        "graph_health": graph_health,
    }


def _scan_pending_drafts(vault_root: Path) -> list[dict]:
    """Walk the vault for `.md.draft` files left by the auto-ingest pipeline.
    Returns enriched entries (title, author, published_at) for the review queue."""
    if not vault_root.exists():
        return []
    import frontmatter as _fm
    out: list[dict] = []
    from .config import passes_scope as _passes_scope
    for p in vault_root.rglob("*.md.draft"):
        try:
            rel = str(p.relative_to(vault_root))
        except ValueError:
            continue
        if not _passes_scope(rel):
            continue
        meta: dict = {}
        try:
            post = _fm.loads(p.read_text(encoding="utf-8"))
            meta = post.metadata or {}
        except Exception:                                    # noqa: BLE001
            meta = {}
        out.append({
            "path": rel,
            "title": meta.get("title"),
            "author": meta.get("author"),
            "published_at": meta.get("published_at"),
        })
    return sorted(out, key=lambda d: d["path"])
