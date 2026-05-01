"""Parse + edit `_taxonomy.md` — the controlled tag vocabulary.

The file has two operator-editable sections:
  - "Active tags" — bullet list of `tag` — description.
  - "RENAMES" — one-shot rename directives that the indexer applies on the
    next watch event, then strips out.

Indexer reloads on file change. Renames trigger atomic frontmatter rewrites
across all notes; orphaned tags (in notes but no longer in vocabulary) are
flagged in `_review-queue.md`, not auto-fixed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_TAG_LINE = re.compile(r"^\s*[-*]\s+`([a-z0-9_]+)`\s*(?:[—-]\s*(.*))?$")
_RENAME_LINE = re.compile(r"^\s*([a-z0-9_]+)\s*[→>-]+\s*([a-z0-9_]+)\s*$")


@dataclass
class Taxonomy:
    tags: dict[str, str]                 # name → description
    renames: list[tuple[str, str]]       # (old, new) pairs


def _section(text: str, header: str) -> str:
    """Return the body of the `## <header>` section (until the next ## or EOF)."""
    pattern = re.compile(rf"^##\s+{re.escape(header)}\s*$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    next_h = re.search(r"^##\s+", rest, re.MULTILINE)
    return rest[: next_h.start()] if next_h else rest


def parse(text: str) -> Taxonomy:
    tags: dict[str, str] = {}
    for raw in _section(text, "Active tags").splitlines():
        m = _TAG_LINE.match(raw)
        if m:
            tags[m.group(1)] = (m.group(2) or "").strip()
    renames: list[tuple[str, str]] = []
    for raw in _section(text, "RENAMES (one-shot; remove lines after indexer applies)").splitlines():
        # Skip HTML-comment hint lines and blanks.
        if raw.strip().startswith("<!--") or not raw.strip():
            continue
        m = _RENAME_LINE.match(raw)
        if m:
            renames.append((m.group(1), m.group(2)))
    return Taxonomy(tags=tags, renames=renames)


def parse_file(path: Path) -> Taxonomy:
    if not path.exists():
        return Taxonomy(tags={}, renames=[])
    return parse(path.read_text(encoding="utf-8"))


def strip_renames(text: str, applied: list[tuple[str, str]]) -> str:
    """Return ``text`` with the listed rename directives removed.

    Only removes lines that match an applied rename; preserves comments and
    structure. Idempotent — re-running on the same text is a no-op.
    """
    if not applied:
        return text
    applied_set = {(o, n) for o, n in applied}

    def keep(line: str) -> bool:
        m = _RENAME_LINE.match(line)
        if not m:
            return True
        return (m.group(1), m.group(2)) not in applied_set

    return "\n".join(line for line in text.splitlines() if keep(line)) + ("\n" if text.endswith("\n") else "")
