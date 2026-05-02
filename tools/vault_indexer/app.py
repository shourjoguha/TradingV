"""vault-indexer FastAPI app — port 8001.

Endpoints:
  GET  /health
  POST /reload                 — full vault rescan (idempotent)
  GET  /node/{path:path}       — node metadata + body
  GET  /search?q=&k=           — KNN with decay
  GET  /traverse/{path:path}?depth=2  — local subgraph
  POST /promote                — apply ticks from _review-queue.md, regenerate it
  POST /apply-renames          — apply pending RENAMES from _taxonomy.md
  POST /regenerate-review      — gather suggestions and rewrite the queue file
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from . import cache as _cache
from . import indexer as _indexer
from . import renames as _renames
from . import research_hook as _research_hook
from . import review as _review
from . import search as _search
from . import taxonomy as _tax
from .config import CONFIG

logger = logging.getLogger("vault-indexer")
logging.basicConfig(level=logging.INFO)


_CON = None


def _con():
    global _CON
    if _CON is None:
        _CON = _cache.init(CONFIG.db_path, CONFIG.embedding_dim)
    return _CON


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Validate the vault path; create cache file lazily.
    if not CONFIG.vault_path.exists():
        logger.error("vault not found at %s", CONFIG.vault_path)
        raise RuntimeError(f"vault not found at {CONFIG.vault_path}")
    _ = _con()
    logger.info(
        "vault-indexer up — vault=%s db=%s model=%s",
        CONFIG.vault_path, CONFIG.db_path, CONFIG.embedding_model,
    )
    yield


app = FastAPI(lifespan=lifespan, title="vault-indexer")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "vault": str(CONFIG.vault_path),
        "db": str(CONFIG.db_path),
        "model": CONFIG.embedding_model,
        "embedding_dim": CONFIG.embedding_dim,
    }


@app.post("/reload")
async def reload_vault():
    """Apply pending RENAMES, full rescan, regenerate review queue."""
    rename_log = _renames.apply_renames(
        CONFIG.vault_path, CONFIG.vault_path / "_taxonomy.md"
    )
    stats = _indexer.full_rescan(_con())
    tax = _tax.parse_file(CONFIG.vault_path / "_taxonomy.md")
    suggestions = _review.gather_suggestions(_con(), vocabulary=tax.tags)
    suggestions["rename_log"] = rename_log
    _review.write(CONFIG.vault_path, _review.render(suggestions))
    return {**stats, "renames": rename_log}


@app.get("/node/{path:path}")
async def get_node(path: str):
    node = _cache.get_node(_con(), path)
    if node is None:
        raise HTTPException(404, f"node not found: {path}")
    return node


@app.get("/search")
async def search_endpoint(
    q: str = Query(..., min_length=1),
    k: int = Query(8, ge=1, le=50),
):
    return {"query": q, "k": k, "results": _search.search(_con(), q, k=k)}


@app.get("/traverse/{path:path}")
async def traverse_endpoint(path: str, depth: int = Query(1, ge=1, le=3)):
    """Return the path's node plus first-/second-degree neighbours.

    Edges considered: explicit (parent / wikilink) AND auto-similarity
    (top-K similar nodes).
    """
    node = _cache.get_node(_con(), path)
    if node is None:
        raise HTTPException(404, f"node not found: {path}")
    visited: dict[str, dict] = {path: node}
    frontier = [path]
    for _ in range(depth):
        next_frontier: list[str] = []
        for cur in frontier:
            # Explicit edges.
            for r in _con().execute(
                "SELECT dst_path, kind, weight FROM vault_edge WHERE src_path = ? "
                "UNION ALL "
                "SELECT src_path, kind, weight FROM vault_edge WHERE dst_path = ?",
                (cur, cur),
            ):
                dst, _kind, _w = r
                if dst in visited:
                    continue
                n = _cache.get_node(_con(), dst)
                if n is not None:
                    visited[dst] = n
                    next_frontier.append(dst)
            # Implicit similarity edges.
            for sim in _search.similar_to_node(_con(), cur, k=3, exclude_self=True):
                p = sim["path"]
                if p in visited:
                    continue
                n = _cache.get_node(_con(), p)
                if n is not None:
                    visited[p] = n
                    next_frontier.append(p)
        frontier = next_frontier
        if not frontier:
            break
    return {"root": path, "depth": depth, "nodes": list(visited.values())}


@app.post("/promote")
async def promote_endpoint():
    """Read ticks from `_review-queue.md`, apply them, regenerate the queue.

    Also scans `Research/*.md` for ticked Approve/Dismiss boxes and
    fires the corresponding TradingView API call.
    """
    text = _review.read(CONFIG.vault_path)
    ticks = _review.parse_ticks(text)
    counts = _review.promote(_con(), CONFIG.vault_path, ticks) if ticks else {}
    research_counts = _research_hook.scan_and_apply(CONFIG.vault_path)
    # Re-scan so applied tags + Research ticks are reflected in the cache.
    _indexer.full_rescan(_con())
    tax = _tax.parse_file(CONFIG.vault_path / "_taxonomy.md")
    suggestions = _review.gather_suggestions(_con(), vocabulary=tax.tags)
    _review.write(CONFIG.vault_path, _review.render(suggestions))
    return {"applied": counts, "research": research_counts}


@app.post("/apply-renames")
async def apply_renames_endpoint():
    log = _renames.apply_renames(
        CONFIG.vault_path, CONFIG.vault_path / "_taxonomy.md"
    )
    _indexer.full_rescan(_con())
    return {"renames": log}


@app.post("/regenerate-review")
async def regenerate_review_endpoint():
    tax = _tax.parse_file(CONFIG.vault_path / "_taxonomy.md")
    suggestions = _review.gather_suggestions(_con(), vocabulary=tax.tags)
    _review.write(CONFIG.vault_path, _review.render(suggestions))
    return {"ok": True, "vocabulary_size": len(tax.tags)}
