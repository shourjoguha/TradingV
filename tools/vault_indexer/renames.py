"""Apply tag renames declared in `_taxonomy.md`'s RENAMES block.

For each `old → new` directive: walk the vault, rewrite frontmatter `tags`,
log the count, then strip the directive from the taxonomy file. Atomic per
rename — if one fails, others still apply.
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

from . import indexer as _indexer
from . import taxonomy as _tax
from .config import passes_scope
from .vault import is_indexable


def apply_renames(vault_root: Path, taxonomy_file: Path) -> list[tuple[str, str, int]]:
    """Apply every rename in the RENAMES block. Returns log of (old, new, n_rewrites)."""
    tax = _tax.parse_file(taxonomy_file)
    if not tax.renames:
        return []

    rewrites: list[tuple[str, str, int]] = []
    applied: list[tuple[str, str]] = []

    for old, new in tax.renames:
        n = 0
        for md in vault_root.rglob("*.md"):
            if not is_indexable(md, vault_root):
                continue
            if not passes_scope(str(md.relative_to(vault_root))):
                continue
            text = md.read_text(encoding="utf-8")
            try:
                post = frontmatter.loads(text)
            except Exception:                          # noqa: BLE001
                continue
            tags = list(post.metadata.get("tags") or [])
            if old not in tags:
                continue
            new_tags = [new if t == old else t for t in tags]
            # Dedupe in case 'new' was already present.
            seen: set[str] = set()
            deduped = [t for t in new_tags if not (t in seen or seen.add(t))]
            post["tags"] = deduped
            md.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
            n += 1
        rewrites.append((old, new, n))
        applied.append((old, new))

    # Strip applied directives from the taxonomy file.
    if applied:
        text = taxonomy_file.read_text(encoding="utf-8")
        new_text = _tax.strip_renames(text, applied)
        if new_text != text:
            taxonomy_file.write_text(new_text, encoding="utf-8")

    return rewrites
