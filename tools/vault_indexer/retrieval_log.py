"""Retrieval log — the measurement substrate (retrieval-depth Phase 0).

Records, per search call, what was *eligible* vs what was *surfaced*, and the
reason each eligible-but-dropped candidate didn't make the cut. This is the
instrument that breaks the master-multiplier limitation C1 ("no recall ground
truth"): without it, every retrieval gap is invisible. With it, we can quantify
the recall delta between the fast path and the deep mode (Phase 1) and prove
whether deeper retrieval actually surfaces things the fast path drops.

Storage: a table in the indexer's own sqlite cache DB (same DB ``search`` runs
against), so there is zero cross-process coupling. Writes are one INSERT + one
bounded DELETE — sub-millisecond — and the whole path is wrapped by the caller
in try/except so a logging failure can NEVER break search (invariant #2: the
always-on fast path stays cheap and robust).

Toggle with ``RETRIEVAL_LOG_ENABLED=0``. Cap rows with ``RETRIEVAL_LOG_MAX_ROWS``
(default 5000) — oldest rows are pruned on each write.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Optional, Sequence


_SCHEMA = """
CREATE TABLE IF NOT EXISTS retrieval_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  domain TEXT,
  mode TEXT NOT NULL,
  query TEXT NOT NULL,
  anchors_json TEXT,
  k INTEGER,
  eligible_count INTEGER NOT NULL,
  surfaced_count INTEGER NOT NULL,
  surfaced_json TEXT,
  dropped_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_retrieval_log_ts ON retrieval_log(ts);
"""


def enabled() -> bool:
    return os.environ.get("RETRIEVAL_LOG_ENABLED", "1") != "0"


def _max_rows() -> int:
    try:
        return max(100, int(os.environ.get("RETRIEVAL_LOG_MAX_ROWS", "5000")))
    except ValueError:
        return 5000


def ensure_schema(con) -> None:
    """Idempotent CREATE TABLE + index. Safe to call on every connection."""
    cur = con.cursor()
    for stmt in [s.strip() for s in _SCHEMA.split(";") if s.strip()]:
        cur.execute(stmt)


def record(
    con,
    *,
    query: str,
    mode: str,
    domain: Optional[str],
    k: Optional[int],
    anchors: Optional[Any] = None,
    eligible_count: int,
    surfaced: Sequence[dict],
    dropped: Sequence[dict],
    max_rows: Optional[int] = None,
) -> None:
    """Append one search record + prune oldest beyond the row cap.

    ``surfaced`` / ``dropped`` are compact dicts; only stable, small fields
    are persisted (path, ord, score/similarity, reason) so the log stays
    lean. This function is defensive — any failure is swallowed — but callers
    SHOULD still wrap it so an import-time or connection error can't surface.
    """
    if not enabled():
        return
    try:
        ensure_schema(con)
        cap = max_rows if max_rows is not None else _max_rows()
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        surfaced_slim = [
            {
                "path": s.get("path"),
                "ord": s.get("ord"),
                "score": s.get("score"),
                "similarity": s.get("similarity"),
            }
            for s in surfaced
        ]
        dropped_slim = [
            {
                "path": d.get("path"),
                "ord": d.get("ord"),
                "reason": d.get("reason"),
                "score": d.get("score"),
            }
            for d in dropped
        ]
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO retrieval_log
              (ts, domain, mode, query, anchors_json, k,
               eligible_count, surfaced_count, surfaced_json, dropped_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                domain,
                mode,
                query,
                json.dumps(anchors) if anchors is not None else None,
                k,
                int(eligible_count),
                len(surfaced_slim),
                json.dumps(surfaced_slim),
                json.dumps(dropped_slim),
            ),
        )
        # Bounded prune: drop everything older than the most recent `cap`
        # rows. One indexed delete; negligible cost.
        cur.execute(
            """
            DELETE FROM retrieval_log
            WHERE id <= (
              SELECT COALESCE(MAX(id), 0) - ? FROM retrieval_log
            )
            """,
            (cap,),
        )
    except Exception:  # noqa: BLE001 — logging must never break search
        pass


def recent(con, *, limit: int = 50) -> list[dict]:
    """Read back recent log rows (newest first). For eval + inspection."""
    ensure_schema(con)
    cur = con.cursor()
    rows = list(
        cur.execute(
            """
            SELECT id, ts, domain, mode, query, anchors_json, k,
                   eligible_count, surfaced_count, surfaced_json, dropped_json
            FROM retrieval_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "ts": r[1],
                "domain": r[2],
                "mode": r[3],
                "query": r[4],
                "anchors": json.loads(r[5]) if r[5] else None,
                "k": r[6],
                "eligible_count": r[7],
                "surfaced_count": r[8],
                "surfaced": json.loads(r[9]) if r[9] else [],
                "dropped": json.loads(r[10]) if r[10] else [],
            }
        )
    return out
