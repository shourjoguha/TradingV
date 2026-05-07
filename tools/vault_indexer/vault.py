"""Vault scanner — walks the markdown tree, parses frontmatter, chunks
bodies, watches for file changes."""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import frontmatter

from .config import CONFIG, is_timely


# Files starting with `_` (review queue, taxonomy) are normally skipped — except
# `_index.md`, which is the operator-authored folder-context vignette and gets
# indexed (without chunk embeddings) so the bundle assembler can prepend it.
def is_indexable(path: Path, vault_root: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    rel = path.relative_to(vault_root)
    if any(part.startswith(".") for part in rel.parts):
        return False
    name = rel.parts[-1]
    if name == "_index.md":
        return True
    if name.startswith("_"):
        return False
    return True


@dataclass
class VaultNode:
    rel_path: str                       # e.g. "Newsletters/lyn-alden/2026-w19.md"
    abs_path: Path
    kind: str
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    ingested_at: Optional[str]
    horizon_months: Optional[int]
    parent_path: Optional[str]
    tags: list[str] = field(default_factory=list)
    body_md: str = ""
    body_hash: str = ""

    def is_timely(self) -> bool:
        return is_timely(self.rel_path)


def _infer_kind(rel_path: str) -> str:
    head = rel_path.split("/", 1)[0]
    return {
        "Books": "book_chapter",
        "Newsletters": "newsletter",
        "Videos": "video",
        "Notes": "note",
        "Topics": "topic",
    }.get(head, "note")


def parse_file(path: Path, vault_root: Path) -> VaultNode:
    rel = str(path.relative_to(vault_root))
    text = path.read_text(encoding="utf-8")
    fm = frontmatter.loads(text)
    body = fm.content
    meta = fm.metadata
    # `_index.md` files are always folder context regardless of frontmatter,
    # so the operator can't accidentally pollute the evidence pool by mis-labelling.
    if Path(rel).name == "_index.md":
        kind = "folder_context"
    else:
        kind = meta.get("kind") or _infer_kind(rel)
    horizon = meta.get("horizon_months")
    if horizon is None and is_timely(rel):
        horizon = CONFIG.default_horizon_months
    elif horizon is False or horizon == "null":
        horizon = None  # explicit override → timeless even if in a timely folder

    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return VaultNode(
        rel_path=rel,
        abs_path=path,
        kind=kind,
        title=meta.get("title") or path.stem,
        author=meta.get("author"),
        published_at=_to_iso_date(meta.get("published_at")),
        ingested_at=_to_iso_ts(meta.get("ingested_at")),
        horizon_months=horizon,
        parent_path=meta.get("parent"),
        tags=list(meta.get("tags") or []),
        body_md=body,
        body_hash=body_hash,
    )


def _to_iso_date(v) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()[:10]
    return str(v)[:10]


def _to_iso_ts(v) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v.isoformat()
    return str(v)


def scan(vault_root: Path) -> Iterable[VaultNode]:
    for p in vault_root.rglob("*.md"):
        if not is_indexable(p, vault_root):
            continue
        try:
            yield parse_file(p, vault_root)
        except Exception as e:                          # noqa: BLE001
            # Don't kill the whole scan on one bad file; log + skip.
            print(f"[vault] failed to parse {p}: {e}")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_body(body: str, *, target_tokens: int, overlap_tokens: int) -> list[tuple[str, Optional[str]]]:
    """Naive token-approximation chunker. Splits on heading boundaries first;
    long sections are subdivided to ~``target_tokens`` words each with
    ``overlap_tokens`` word overlap between consecutive chunks.

    Returns list of (text, section_label).
    """
    if not body.strip():
        return []
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in body.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            sections.append((heading, []))
        else:
            sections[-1][1].append(line)

    out: list[tuple[str, Optional[str]]] = []
    for heading, lines in sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        words = text.split()
        if len(words) <= target_tokens:
            out.append((text, heading or None))
            continue
        # Sliding window over words.
        i = 0
        while i < len(words):
            piece = " ".join(words[i : i + target_tokens])
            out.append((piece, heading or None))
            if i + target_tokens >= len(words):
                break
            i += max(1, target_tokens - overlap_tokens)
    return out
