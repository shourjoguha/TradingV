"""Indexer pipeline — orchestrates parse → chunk → embed → cache.

Single-flight ingestion of one or many vault files. Diff-aware: compares
``body_hash`` against the stored value and skips embedding when unchanged.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Iterable

import frontmatter

from . import aliases as _aliases
from . import cache as _cache
from . import citations as _citations
from . import embed as _embed
from .config import CONFIG
from .vault import VaultNode, parse_file, scan, chunk_body, is_indexable

# Per-process alias map. One sidecar = one domain, so load once at module import.
# Refreshable via :func:`reload_alias_map` if `_aliases-<domain>.md` is edited
# while the sidecar is running (called from /reload).
_ALIAS_MAP: dict[str, str] | None = None


def _alias_map() -> dict[str, str]:
    global _ALIAS_MAP
    if _ALIAS_MAP is None:
        _ALIAS_MAP = _aliases.load_alias_map(CONFIG.vault_path, CONFIG.domain)
    return _ALIAS_MAP


def reload_alias_map() -> dict[str, str]:
    """Force re-read of `_aliases-<domain>.md`. Called by /reload."""
    global _ALIAS_MAP
    _ALIAS_MAP = _aliases.load_alias_map(CONFIG.vault_path, CONFIG.domain)
    return _ALIAS_MAP


def _now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


def index_one(con, node: VaultNode, *, force: bool = False) -> bool:
    """Index a single vault node. Returns True if embeddings were (re)computed.

    ``force=True`` re-embeds even when the body hash matches.
    """
    existing = _cache.get_node(con, node.rel_path)
    if existing and existing["body_hash"] == node.body_hash and not force:
        # Even when content unchanged, frontmatter (tags, horizon) may have
        # moved — refresh metadata only.
        with _cache.transaction(con) as cur:
            _cache.upsert_node(
                cur,
                path=node.rel_path,
                kind=node.kind,
                title=node.title,
                author=node.author,
                published_at=node.published_at,
                ingested_at=node.ingested_at,
                horizon_months=node.horizon_months,
                parent_path=node.parent_path,
                tags=node.tags,
                body_hash=node.body_hash,
                body_md=node.body_md,
                last_indexed_at=_now_iso(),
                evergreen=node.evergreen,
            )
        return False

    # Folder-context vignettes (`_index.md`) are stored as nodes for body lookup
    # but never embedded — they don't compete in the evidence KNN pool.
    if node.kind == "folder_context":
        chunks: list[tuple[str, str | None]] = []
        embeddings: list = []
    else:
        chunks = chunk_body(
            node.body_md,
            target_tokens=CONFIG.chunk_target_tokens,
            overlap_tokens=CONFIG.chunk_overlap_tokens,
        )
        texts = [t for t, _ in chunks]
        embeddings = _embed.encode_passages(texts) if texts else []

    with _cache.transaction(con) as cur:
        _cache.upsert_node(
            cur,
            path=node.rel_path,
            kind=node.kind,
            title=node.title,
            author=node.author,
            published_at=node.published_at,
            ingested_at=node.ingested_at,
            horizon_months=node.horizon_months,
            parent_path=node.parent_path,
            tags=node.tags,
            body_hash=node.body_hash,
            body_md=node.body_md,
            last_indexed_at=_now_iso(),
            evergreen=node.evergreen,
        )
        _cache.replace_chunks(
            cur,
            node.rel_path,
            [
                (i, text, section, emb)
                for i, ((text, section), emb) in enumerate(zip(chunks, embeddings))
            ],
        )
        # Build edge batch: parent (if any) + extracted citations + temporal.
        # 'wikilink' rows (operator-approved cross-links from review queue) are
        # NOT touched here — replace_edges_by_kinds preserves them.
        new_edges: list[tuple[str, str, float]] = []
        if node.parent_path:
            new_edges.append((node.parent_path, "parent", 1.0))
        if node.kind != "folder_context":
            citation_edges, _dead = _citations.parse_citations(
                node.body_md,
                node.rel_path,
                alias_map=_alias_map(),
                con=con,
            )
            new_edges.extend(citation_edges)
        _cache.replace_edges_by_kinds(
            cur,
            node.rel_path,
            _citations.INDEXER_OWNED_KINDS,
            new_edges,
        )
    return True


def full_rescan(con) -> dict:
    """Walk the vault, ingest changed/new notes, drop stale ones."""
    seen: set[str] = set()
    changed = 0
    unchanged = 0
    for node in scan(CONFIG.vault_path):
        seen.add(node.rel_path)
        if index_one(con, node):
            changed += 1
        else:
            unchanged += 1
    # Drop nodes whose files disappeared.
    dropped = 0
    for path in _cache.all_node_paths(con):
        if path not in seen:
            with _cache.transaction(con) as cur:
                _cache.delete_node(cur, path)
            dropped += 1
    return {"changed": changed, "unchanged": unchanged, "dropped": dropped}


def write_frontmatter(node_path: Path, *, tags: list[str] | None = None) -> None:
    """Re-serialize a vault file with updated frontmatter fields.

    Only the fields the indexer manages on behalf of the operator are
    rewritten (currently: tags). Other metadata is preserved as-is.
    """
    text = node_path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    if tags is not None:
        post["tags"] = tags
    node_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
