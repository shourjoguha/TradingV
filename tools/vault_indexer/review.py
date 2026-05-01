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


REVIEW_FILE = "_review-queue.md"

# `- [ ] tag: name` / `- [x] tag: name` / `- [ ] link → other.md (sim 0.8)` etc.
_CHECKBOX = re.compile(r"^\s*- \[(?P<state>[ xX])\] (?P<rest>.*)$")
_TAG_RE = re.compile(r"tag:\s*`?(?P<tag>[a-z0-9_]+)`?")
_LINK_RE = re.compile(r"link\s*(?:→|->)\s*(?P<dst>[^\s(]+)")


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

    rename_log = suggestions.get("rename_log") or []
    if rename_log:
        lines.append("## Renames applied")
        lines.append("")
        for old, new, count in rename_log:
            lines.append(f"- `{old}` → `{new}` (rewrote {count} note(s))")
        lines.append("")

    if not (auto_tags or cross_links or orphans or rename_log):
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
    """
    counts = {"tags_added": 0, "links_added": 0, "skipped": 0}
    by_path: dict[str, list[str]] = {}
    edges: list[tuple[str, str, str, float]] = []
    for kind, payload in ticks:
        if kind == "tag":
            by_path.setdefault(payload["path"], []).append(payload["tag"])
        elif kind == "link":
            edges.append((payload["src"], payload["dst"], "wikilink", 1.0))

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
    return counts


def gather_suggestions(
    con,
    *,
    vocabulary: dict[str, str],
    similarity_threshold: float = 0.78,
    cross_link_per_node: int = 3,
) -> dict:
    """Build the suggestions dict for a fresh review queue."""
    from . import auto_tag as _auto

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
        # Cross-link suggestions per-note.
        sims = _search.similar_to_node(con, path, k=cross_link_per_node, exclude_self=True)
        sims = [(p, s) for p, s in sims if s >= similarity_threshold]
        if sims:
            cross_links[path] = sims
        # Orphan tags — tags on this note that aren't in vocabulary.
        for t in existing_tags:
            if t not in vocabulary:
                orphan_count[t] = orphan_count.get(t, 0) + 1

    orphans = sorted(orphan_count.items(), key=lambda kv: -kv[1])
    return {
        "auto_tags": auto_tags,
        "cross_links": cross_links,
        "orphan_tags": orphans,
    }
