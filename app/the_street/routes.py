"""HTTP routes for The Street (smart-money snapshots).

Thin async-wrapper around :mod:`tools.the_street.query` so the frontend
can render the snapshot tier tables, per-ticker timelines, and the
snapshot browser without touching the indexer port directly. The wrapped
functions are pure-IO over the vault filesystem; we run them in a thread
to keep the event loop unblocked.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from tools.the_street import build_digests as _digests
from tools.the_street import query as _q


router = APIRouter(prefix="/the-street", tags=["the-street"])


def _vault_path() -> Path:
    """Resolved vault root. Read each call so a test can monkeypatch
    ``tools.the_street.query.DEFAULT_VAULT`` between requests."""
    return _q.DEFAULT_VAULT


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

@router.get("/snapshots")
async def list_snapshots(_api_key: str = Depends(verify_api_key)) -> dict:
    snaps = await asyncio.to_thread(_q.list_snapshots, _vault_path())
    return {
        "items": [
            {
                "date": s.date,
                "writeup_dir": str(s.writeup_dir),
                "data_dir": str(s.data_dir),
                "vault_path": f"The Street/snapshots/{s.date}/_index.md",
            }
            for s in snaps
        ],
        "count": len(snaps),
    }


# ---------------------------------------------------------------------------
# Ticker timeline
# ---------------------------------------------------------------------------

@router.get("/ticker/{ticker}")
async def ticker_history(
    ticker: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    rows = await asyncio.to_thread(_q.find_ticker, ticker, _vault_path())
    return {"ticker": ticker.upper(), "items": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Tier listing
# ---------------------------------------------------------------------------

@router.get("/tier/{tier}")
async def tier_list(
    tier: int,
    date: Optional[str] = Query(default=None, description="Snapshot date YYYY-MM-DD; defaults to latest."),
    include_etfs: bool = Query(default=False),
    _api_key: str = Depends(verify_api_key),
) -> dict:
    if tier not in (1, 2, 3):
        raise HTTPException(400, f"tier must be 1, 2, or 3 — got {tier!r}")

    snaps = await asyncio.to_thread(_q.list_snapshots, _vault_path())
    if not snaps:
        return {"tier": tier, "snapshot_date": None, "items": [], "count": 0}

    target = (
        next((s for s in snaps if s.date == date), None) if date else snaps[0]
    )
    if target is None:
        raise HTTPException(404, f"snapshot {date!r} not found")

    rows = await asyncio.to_thread(
        _q.list_tier, tier, target, exclude_etfs=not include_etfs
    )
    return {
        "tier": tier,
        "snapshot_date": target.date,
        "items": rows,
        "count": len(rows),
    }


# ---------------------------------------------------------------------------
# Politician timeline
# ---------------------------------------------------------------------------

@router.get("/politician/{name}")
async def politician_history(
    name: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    rows = await asyncio.to_thread(_q.find_politician, name, _vault_path())
    return {"politician": name, "items": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Per-ticker digest (pre-baked accordion content)
# ---------------------------------------------------------------------------

def _read_or_build_digests(snapshot_date: str) -> dict:
    """Return the parsed ``digests.json`` for the date, building it lazily
    if missing or stale.

    Lazy-build keeps the operator workflow cheap: drop a snapshot in the
    vault → first request rebuilds → subsequent requests hit the cache.
    """
    snaps = _q.list_snapshots(_vault_path())
    target = next((s for s in snaps if s.date == snapshot_date), None)
    if target is None:
        raise HTTPException(404, f"snapshot {snapshot_date!r} not found")

    digest_path = target.data_dir / "digests.json"
    if _digests._is_stale(target.data_dir):  # type: ignore[attr-defined]
        _digests.build_one(target.data_dir, target.date, force=False)

    if not digest_path.exists():
        # Should be unreachable — build_one writes unconditionally — but
        # guard the response shape so the frontend still decodes.
        return {
            "snapshot_date": snapshot_date,
            "generated_at": None,
            "tickers": {},
        }
    return json.loads(digest_path.read_text(encoding="utf-8"))


@router.get("/digest/{snapshot_date}/{ticker}")
async def ticker_digest(
    snapshot_date: str,
    ticker: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Return the per-ticker digest for one snapshot date.

    Pre-baked: the response is a slice of the snapshot's ``digests.json``
    (built once by ``tools.the_street.build_digests`` and cached on disk).
    Powers the Tier-table accordion expand + copy-to-clipboard button.
    """
    blob = await asyncio.to_thread(_read_or_build_digests, snapshot_date)
    entry = (blob.get("tickers") or {}).get(ticker.upper())
    if entry is None:
        return {
            "snapshot_date": snapshot_date,
            "ticker": ticker.upper(),
            "found": False,
            "entry": None,
        }
    return {
        "snapshot_date": snapshot_date,
        "ticker": ticker.upper(),
        "found": True,
        "entry": entry,
    }
