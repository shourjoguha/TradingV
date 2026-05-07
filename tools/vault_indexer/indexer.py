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

from . import cache as _cache
from . import embed as _embed
from .config import CONFIG
from .vault import VaultNode, parse_file, scan, chunk_body, is_indexable


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
        )
        _cache.replace_chunks(
            cur,
            node.rel_path,
            [
                (i, text, section, emb)
                for i, ((text, section), emb) in enumerate(zip(chunks, embeddings))
            ],
        )
        # Parent edge — add as 'parent' if specified.
        if node.parent_path:
            _cache.replace_edges(
                cur, node.rel_path,
                [(node.parent_path, "parent", 1.0)],
            )
        else:
            _cache.replace_edges(cur, node.rel_path, [])
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
