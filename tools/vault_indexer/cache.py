"""SQLite + sqlite-vec cache. Vault is canonical; this is rebuildable.

apsw is used (not stdlib sqlite3) because Apple's Python build disables
loadable extensions, which sqlite-vec needs.
"""
from __future__ import annotations

import json
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

import apsw
import sqlite_vec


_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_node (
  path TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT,
  author TEXT,
  published_at TEXT,
  ingested_at TEXT,
  horizon_months INTEGER,
  parent_path TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  body_hash TEXT NOT NULL,
  body_md TEXT NOT NULL,
  last_indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_chunk (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL REFERENCES vault_node(path) ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  text TEXT NOT NULL,
  section TEXT,
  UNIQUE (path, ord)
);

CREATE TABLE IF NOT EXISTS vault_edge (
  src_path TEXT NOT NULL,
  dst_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (src_path, dst_path, kind)
);

-- Graph layer: per-edge metadata (context snippet at link site, created_at).
-- Optional sibling to vault_edge -- rows present only when context is captured.
CREATE TABLE IF NOT EXISTS vault_edge_meta (
  src_path TEXT NOT NULL,
  dst_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  context_snippet TEXT,
  created_at TEXT,
  PRIMARY KEY (src_path, dst_path, kind)
);

CREATE INDEX IF NOT EXISTS ix_vault_chunk_path ON vault_chunk(path);
CREATE INDEX IF NOT EXISTS ix_vault_edge_dst ON vault_edge(dst_path);
CREATE INDEX IF NOT EXISTS ix_vault_edge_kind ON vault_edge(kind);
"""

# Graph-layer columns added to vault_node via idempotent migration in init().
# Per-document scores written by graph_compute.recompute(); NULL until first run
# or in domains below the min_edges threshold (graceful degradation).
_GRAPH_NODE_COLUMNS = (
    ("citation_rank", "REAL DEFAULT NULL"),
    ("centrality", "REAL DEFAULT NULL"),
    ("cluster_id", "INTEGER DEFAULT NULL"),
)

# Decay-layer columns added to vault_node via idempotent migration in init().
# - `evergreen` (NULL / 0 / 1): operator-set or path-glob-default. NULL = not yet
#   classified (treated as non-evergreen by decay.weight_for, will be backfilled
#   on next /reload). Used by Phase E Commit 2 ranked-grouped decay model.
_DECAY_NODE_COLUMNS = (
    ("evergreen", "INTEGER DEFAULT NULL"),
)


def _connect(db_path: Path) -> apsw.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = apsw.Connection(str(db_path))
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    # WAL allows readers to proceed during a write transaction (graph recompute
    # commits scores under one short transaction; without WAL, MCP /search calls
    # would block). synchronous=NORMAL trades a small durability window for
    # write throughput; safe for a rebuildable cache.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _ensure_graph_columns(cur: apsw.Cursor) -> None:
    """Idempotently add graph-layer columns to vault_node.

    apsw has no ``ADD COLUMN IF NOT EXISTS``; PRAGMA table_info is the portable
    check. Safe to run on every startup.
    """
    existing = {r[1] for r in cur.execute("PRAGMA table_info(vault_node)")}
    for col, defn in _GRAPH_NODE_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE vault_node ADD COLUMN {col} {defn}")


def _ensure_decay_columns(cur: apsw.Cursor) -> None:
    """Idempotently add decay-layer columns to vault_node.

    Parallel to :func:`_ensure_graph_columns`. Safe to run on every startup.
    """
    existing = {r[1] for r in cur.execute("PRAGMA table_info(vault_node)")}
    for col, defn in _DECAY_NODE_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE vault_node ADD COLUMN {col} {defn}")


def backfill_evergreen(con: apsw.Connection, classify) -> int:
    """Set ``vault_node.evergreen`` for all rows where it is currently NULL.

    ``classify`` is a callable ``(rel_path: str) -> Optional[bool]`` —
    typically ``CONFIG.is_evergreen_path``. Returns the row count that was
    updated.

    Cheap (single table scan, one UPDATE per row), idempotent (only touches
    NULL rows). Called from indexer boot path after schema migration so the
    pre-Phase-E.2 corpus picks up the new evergreen classification without
    a full re-ingest.
    """
    cur = con.cursor()
    rows = list(cur.execute(
        "SELECT path FROM vault_node WHERE evergreen IS NULL"
    ))
    if not rows:
        return 0
    updates: list[tuple[Optional[int], str]] = []
    for (path,) in rows:
        verdict = classify(path)
        if verdict is None:
            # No globs configured for this domain; leave NULL → decay treats
            # as non-evergreen (rank applies). This is the "no opinion" state.
            continue
        updates.append((1 if verdict else 0, path))
    if not updates:
        return 0
    cur.executemany(
        "UPDATE vault_node SET evergreen = ? WHERE path = ?",
        updates,
    )
    return len(updates)


def init(db_path: Path, embedding_dim: int) -> apsw.Connection:
    """Create schema + the sqlite-vec virtual table sized to ``embedding_dim``."""
    con = _connect(db_path)
    cur = con.cursor()
    for stmt in [s.strip() for s in _SCHEMA.split(";") if s.strip()]:
        cur.execute(stmt)
    cur.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vault_chunk_vec USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{embedding_dim}])"
    )
    _ensure_graph_columns(cur)
    _ensure_decay_columns(cur)
    # Phase E Commit 4: FTS5 lexical index. Created idempotently; populated
    # via :func:`lexical.rebuild` on /reload (not here, to keep init fast).
    from . import lexical as _lexical
    _lexical.init_fts(con)
    return con


def f32_blob(vec) -> bytes:
    """Pack a sequence of floats as little-endian float32 — the format
    sqlite-vec expects for FLOAT[N] columns."""
    return struct.pack(f"{len(vec)}f", *vec)


@contextmanager
def transaction(con: apsw.Connection):
    cur = con.cursor()
    cur.execute("BEGIN")
    try:
        yield cur
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


def upsert_node(
    cur: apsw.Cursor,
    *,
    path: str,
    kind: str,
    title: Optional[str],
    author: Optional[str],
    published_at: Optional[str],
    ingested_at: Optional[str],
    horizon_months: Optional[int],
    parent_path: Optional[str],
    tags: list[str],
    body_hash: str,
    body_md: str,
    last_indexed_at: str,
    evergreen: Optional[bool] = None,
) -> None:
    """Upsert a vault_node row.

    ``evergreen`` is tri-state: ``True`` (always weight=1.0 in decay), ``False``
    (subject to per-author ranked decay), ``None`` (not yet classified — backfill
    on next ingest will resolve via path-glob default).
    """
    evergreen_int = None if evergreen is None else (1 if evergreen else 0)
    cur.execute(
        """
        INSERT INTO vault_node (path, kind, title, author, published_at,
            ingested_at, horizon_months, parent_path, tags, body_hash,
            body_md, last_indexed_at, evergreen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            kind=excluded.kind,
            title=excluded.title,
            author=excluded.author,
            published_at=excluded.published_at,
            ingested_at=excluded.ingested_at,
            horizon_months=excluded.horizon_months,
            parent_path=excluded.parent_path,
            tags=excluded.tags,
            body_hash=excluded.body_hash,
            body_md=excluded.body_md,
            last_indexed_at=excluded.last_indexed_at,
            evergreen=excluded.evergreen
        """,
        (
            path, kind, title, author, published_at, ingested_at,
            horizon_months, parent_path, json.dumps(tags), body_hash,
            body_md, last_indexed_at, evergreen_int,
        ),
    )


def replace_chunks(
    cur: apsw.Cursor,
    path: str,
    chunks: list[tuple[int, str, Optional[str], list[float]]],
) -> None:
    """Drop all chunks for ``path``, reinsert + reindex embeddings + sync FTS.

    chunks: list of (ord, text, section, embedding_floats).
    """
    # Drop old vec rows first (the FK from vault_chunk → ON DELETE CASCADE
    # handles vault_chunk; but vault_chunk_vec is a virtual table without
    # FK — wipe by chunk_id explicitly).
    old_ids = [
        r[0]
        for r in cur.execute("SELECT id FROM vault_chunk WHERE path = ?", (path,))
    ]
    if old_ids:
        cur.executemany(
            "DELETE FROM vault_chunk_vec WHERE chunk_id = ?",
            [(i,) for i in old_ids],
        )
    cur.execute("DELETE FROM vault_chunk WHERE path = ?", (path,))

    for ord_, text, section, embedding in chunks:
        cur.execute(
            "INSERT INTO vault_chunk (path, ord, text, section) VALUES (?, ?, ?, ?)",
            (path, ord_, text, section),
        )
        chunk_id = cur.execute("SELECT last_insert_rowid()").fetchone()[0]
        cur.execute(
            "INSERT INTO vault_chunk_vec (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, f32_blob(embedding)),
        )

    # Phase E Commit 6 (2026-05-16): keep FTS in step with vault_chunk on every
    # write so operator-added content is searchable via lexical immediately,
    # not on next /reload sweep. Lazy import avoids circular (lexical → cache).
    from . import lexical as _lexical
    _lexical.sync_chunks_for_path(cur, path)


def delete_node(cur: apsw.Cursor, path: str) -> None:
    old_ids = [
        r[0]
        for r in cur.execute("SELECT id FROM vault_chunk WHERE path = ?", (path,))
    ]
    if old_ids:
        cur.executemany(
            "DELETE FROM vault_chunk_vec WHERE chunk_id = ?",
            [(i,) for i in old_ids],
        )
    cur.execute("DELETE FROM vault_node WHERE path = ?", (path,))
    cur.execute("DELETE FROM vault_edge WHERE src_path = ? OR dst_path = ?", (path, path))
    # Sync FTS: drop the lexical rows so deleted paths can't surface in search.
    from . import lexical as _lexical
    _lexical.delete_path(cur, path)


def replace_edges(cur: apsw.Cursor, src_path: str, edges: Iterable[tuple[str, str, float]]) -> None:
    """Replace ALL edges for ``src_path`` with the given list.

    Destructive: wipes every edge regardless of kind. Use
    :func:`replace_edges_by_kinds` when you only want to manage a subset
    (e.g. preserving operator-approved ``wikilink`` rows during re-indexing).
    """
    cur.execute("DELETE FROM vault_edge WHERE src_path = ?", (src_path,))
    cur.executemany(
        "INSERT OR REPLACE INTO vault_edge (src_path, dst_path, kind, weight) VALUES (?, ?, ?, ?)",
        [(src_path, dst, kind, weight) for dst, kind, weight in edges],
    )


def replace_edges_by_kinds(
    cur: apsw.Cursor,
    src_path: str,
    kinds: Iterable[str],
    edges: Iterable[tuple[str, str, float]],
) -> None:
    """Replace edges for ``src_path`` only for the given ``kinds``.

    Other kinds (e.g. ``wikilink`` rows owned by the review queue) are
    preserved across re-indexing. ``edges`` may include any kinds; only
    rows whose existing kind is in ``kinds`` are deleted before insert.
    """
    kinds_tuple = tuple(kinds)
    if kinds_tuple:
        placeholders = ",".join(["?"] * len(kinds_tuple))
        cur.execute(
            f"DELETE FROM vault_edge WHERE src_path = ? AND kind IN ({placeholders})",
            (src_path, *kinds_tuple),
        )
    cur.executemany(
        "INSERT OR REPLACE INTO vault_edge (src_path, dst_path, kind, weight) VALUES (?, ?, ?, ?)",
        [(src_path, dst, kind, weight) for dst, kind, weight in edges],
    )


def total_edge_count(con: apsw.Connection) -> int:
    """Total edge count across all kinds. Used by hybrid scorer's
    graceful-degradation floor (``min_edges_for_hybrid``).
    """
    row = list(con.execute("SELECT COUNT(*) FROM vault_edge"))
    return int(row[0][0]) if row else 0


def edge_counts_by_kind(con: apsw.Connection) -> dict[str, int]:
    """Per-kind edge counts. Surfaced in graph-health diagnostics."""
    return {
        kind: int(count)
        for kind, count in con.execute(
            "SELECT kind, COUNT(*) FROM vault_edge GROUP BY kind"
        )
    }


def get_node(con: apsw.Connection, path: str) -> Optional[dict]:
    rows = list(con.execute(
        "SELECT path, kind, title, author, published_at, ingested_at, "
        "horizon_months, parent_path, tags, body_hash, body_md, last_indexed_at, "
        "evergreen "
        "FROM vault_node WHERE path = ?",
        (path,),
    ))
    if not rows:
        return None
    r = rows[0]
    return {
        "path": r[0],
        "kind": r[1],
        "title": r[2],
        "author": r[3],
        "published_at": r[4],
        "ingested_at": r[5],
        "horizon_months": r[6],
        "parent_path": r[7],
        "tags": json.loads(r[8]),
        "body_hash": r[9],
        "body_md": r[10],
        "last_indexed_at": r[11],
        "evergreen": None if r[12] is None else bool(r[12]),
    }


def all_node_paths(con: apsw.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT path FROM vault_node")]


def get_chunks(
    con: apsw.Connection,
    path: str,
    *,
    offset: int = 0,
    limit: Optional[int] = None,
) -> list[dict]:
    """Return chunks for ``path``, ordered by ``ord``. Optional offset/limit.

    Chunks come from the same `vault_chunk` rows the embedder writes during
    indexing — no recompute. Returns ``[]`` for nodes that have no chunks
    (e.g. ``kind=folder_context`` nodes are deliberately stored without
    chunks; very short notes may chunk to nothing).
    """
    sql = (
        "SELECT ord, text, section FROM vault_chunk "
        "WHERE path = ? ORDER BY ord ASC"
    )
    params: tuple = (path,)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (path, int(limit), int(offset))
    elif offset:
        # OFFSET without LIMIT is non-standard; SQLite needs a LIMIT to
        # honour OFFSET, so pass a sentinel "no real cap" value.
        sql += " LIMIT -1 OFFSET ?"
        params = (path, int(offset))
    return [
        {"ord": r[0], "text": r[1], "section": r[2]}
        for r in con.execute(sql, params)
    ]


def count_chunks(con: apsw.Connection, path: str) -> int:
    row = list(
        con.execute("SELECT COUNT(*) FROM vault_chunk WHERE path = ?", (path,))
    )
    return int(row[0][0]) if row else 0


def get_chunk_at_ord(
    con: apsw.Connection, path: str, ord_: int,
) -> Optional[dict]:
    """Return a single chunk row by (path, ord), or None if not found.

    Used by search.py's pure-lexical enrichment pass: when a chunk surfaces
    in the FTS leg but not in the vector top-K, we look up its text +
    section on demand for display.
    """
    rows = list(con.execute(
        "SELECT ord, text, section FROM vault_chunk "
        "WHERE path = ? AND ord = ? LIMIT 1",
        (path, int(ord_)),
    ))
    if not rows:
        return None
    r = rows[0]
    return {"ord": r[0], "text": r[1], "section": r[2]}


def folder_contexts_for(con: apsw.Connection, paths: list[str]) -> list[dict]:
    """For each evidence path, walk up the directory tree and collect every
    `_index.md` (kind='folder_context') node that exists in the cache. Returns
    a deduped list ordered root-first, with each entry carrying the list of
    evidence paths it applies to."""
    if not paths:
        return []
    # Build the candidate set: for each evidence path, every ancestor `_index.md`.
    candidates: dict[str, set[str]] = {}        # ctx_path -> evidence_paths it covers
    for ev in paths:
        parts = ev.split("/")
        # Drop the leaf (the evidence file itself); only ancestor folders host vignettes.
        for i in range(len(parts) - 1, -1, -1):
            prefix = "/".join(parts[:i])
            ctx = f"{prefix}/_index.md" if prefix else "_index.md"
            candidates.setdefault(ctx, set()).add(ev)
    # Filter to existing nodes of kind=folder_context.
    placeholders = ",".join(["?"] * len(candidates))
    rows = list(con.execute(
        f"SELECT path, title, body_md FROM vault_node "
        f"WHERE kind = 'folder_context' AND path IN ({placeholders})",
        list(candidates.keys()),
    ))
    found = {r[0]: (r[1], r[2]) for r in rows}
    out: list[dict] = []
    # Order root-first by path depth (shorter = closer to root).
    for ctx_path in sorted(found.keys(), key=lambda p: p.count("/")):
        title, body = found[ctx_path]
        out.append({
            "path": ctx_path,
            "title": title,
            "body": body,
            "applies_to": sorted(candidates[ctx_path]),
        })
    return out
