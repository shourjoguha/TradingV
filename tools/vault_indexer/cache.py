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

CREATE INDEX IF NOT EXISTS ix_vault_chunk_path ON vault_chunk(path);
CREATE INDEX IF NOT EXISTS ix_vault_edge_dst ON vault_edge(dst_path);
"""


def _connect(db_path: Path) -> apsw.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = apsw.Connection(str(db_path))
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    con.execute("PRAGMA foreign_keys = ON")
    return con


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
) -> None:
    cur.execute(
        """
        INSERT INTO vault_node (path, kind, title, author, published_at,
            ingested_at, horizon_months, parent_path, tags, body_hash,
            body_md, last_indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            last_indexed_at=excluded.last_indexed_at
        """,
        (
            path, kind, title, author, published_at, ingested_at,
            horizon_months, parent_path, json.dumps(tags), body_hash,
            body_md, last_indexed_at,
        ),
    )


def replace_chunks(
    cur: apsw.Cursor,
    path: str,
    chunks: list[tuple[int, str, Optional[str], list[float]]],
) -> None:
    """Drop all chunks for ``path``, reinsert + reindex embeddings.

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


def replace_edges(cur: apsw.Cursor, src_path: str, edges: Iterable[tuple[str, str, float]]) -> None:
    cur.execute("DELETE FROM vault_edge WHERE src_path = ?", (src_path,))
    cur.executemany(
        "INSERT OR REPLACE INTO vault_edge (src_path, dst_path, kind, weight) VALUES (?, ?, ?, ?)",
        [(src_path, dst, kind, weight) for dst, kind, weight in edges],
    )


def get_node(con: apsw.Connection, path: str) -> Optional[dict]:
    rows = list(con.execute(
        "SELECT path, kind, title, author, published_at, ingested_at, "
        "horizon_months, parent_path, tags, body_hash, body_md, last_indexed_at "
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
    }


def all_node_paths(con: apsw.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT path FROM vault_node")]
