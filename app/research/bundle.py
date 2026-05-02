"""Build the LLM input bundle: hypotheses + evidence + macro + accuracy.

Hard-truncates to a token budget so prompts stay cache-friendly and cost
predictable. Truncation order: oldest evaluations → lowest-score excerpts.
"""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.hypotheses import service as hyp_service
from app.hypotheses.models import (
    STATUS_ACTIVE,
    Hypothesis,
    HypothesisEvaluation,
    HypothesisNodeLink,
)
from app.macro.models import MacroSeries
from app.macro.service import compute_ratio

logger = logging.getLogger(__name__)


VAULT_INDEXER_URL = os.environ.get("VAULT_INDEXER_URL", "http://localhost:8001")
DEFAULT_K = int(os.environ.get("RESEARCH_BUNDLE_K", "12"))
HARD_TOKEN_CAP = int(os.environ.get("RESEARCH_BUNDLE_TOKEN_CAP", "8000"))


# ----- Hypothesis cards ----------------------------------------------------

async def _hypothesis_cards(
    session: AsyncSession, slugs: Optional[list[str]]
) -> list[dict[str, Any]]:
    if slugs:
        rows = (
            await session.execute(
                select(Hypothesis).where(Hypothesis.slug.in_(slugs))
            )
        ).scalars().all()
    else:
        rows = await hyp_service.list_(session, status=STATUS_ACTIVE)
    cards: list[dict[str, Any]] = []
    for h in rows:
        evals = await hyp_service.recent_evaluations(session, h.id, limit=3)
        link_rows = (
            await session.execute(
                select(HypothesisNodeLink).where(
                    HypothesisNodeLink.hypothesis_id == h.id
                )
            )
        ).scalars().all()
        cards.append({
            "slug": h.slug,
            "id": h.id,
            "title": h.title,
            "claim_type": h.claim_type,
            "axis": h.axis,
            "status": h.status,
            "expires_at": h.expires_at.isoformat() if h.expires_at else None,
            "primary_metric": h.primary_metric,
            "tracking_signal": h.tracking_signal,
            "invalidator": h.invalidator,
            "linked_vault_paths": [r.vault_path for r in link_rows],
            "recent_evaluations": [
                {
                    "evaluated_at": e.evaluated_at.isoformat(),
                    "status_before": e.status_before,
                    "status_after": e.status_after,
                    "reason": e.reason,
                }
                for e in evals
            ],
        })
    return cards


# ----- Evidence retrieval --------------------------------------------------

async def _retrieve_evidence(
    query: str,
    cards: list[dict[str, Any]],
    *,
    k: int = DEFAULT_K,
) -> list[dict[str, Any]]:
    """Hit the vault-indexer for top-k chunks. Prefer linked paths if any
    exist on the hypothesis cards; otherwise generic search on query."""
    linked_paths: set[str] = set()
    for c in cards:
        for p in c.get("linked_vault_paths") or []:
            linked_paths.add(p)

    out: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{VAULT_INDEXER_URL}/search",
                params={"q": query, "k": k * 2 if linked_paths else k},
            )
            r.raise_for_status()
            data = r.json()
            for hit in data.get("results", []):
                if linked_paths and hit["path"] not in linked_paths:
                    continue
                out.append({
                    "vault_path": hit["path"],
                    "title": hit.get("title"),
                    "kind": hit.get("kind"),
                    "section": hit.get("section"),
                    "text": (hit.get("text") or "")[:800],
                    "published_at": hit.get("published_at"),
                    "author": hit.get("author"),
                    "similarity": hit.get("similarity", 0.0),
                    "decay_weight": hit.get("decay_weight", 1.0),
                    "score": hit.get("score", 0.0),
                })
    except Exception as e:                          # noqa: BLE001
        logger.warning("vault-indexer search failed: %s", e)
        return []

    # If linked-only filter starved the result set, fall back to broader.
    if linked_paths and not out:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{VAULT_INDEXER_URL}/search",
                    params={"q": query, "k": k},
                )
                r.raise_for_status()
                data = r.json()
                out = [
                    {
                        "vault_path": h["path"],
                        "title": h.get("title"),
                        "kind": h.get("kind"),
                        "section": h.get("section"),
                        "text": (h.get("text") or "")[:800],
                        "published_at": h.get("published_at"),
                        "author": h.get("author"),
                        "similarity": h.get("similarity", 0.0),
                        "decay_weight": h.get("decay_weight", 1.0),
                        "score": h.get("score", 0.0),
                    }
                    for h in data.get("results", [])
                ]
        except Exception as e:                      # noqa: BLE001
            logger.warning("vault-indexer fallback search failed: %s", e)
    out.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return out[:k]


# ----- Macro snapshot ------------------------------------------------------

async def _macro_snapshot(
    session: AsyncSession, cards: list[dict[str, Any]]
) -> dict[str, Any]:
    """Latest value for each tracking_signal + symbols inside the
    invalidator args. Best-effort — missing symbols just don't appear."""
    symbols: set[str] = set()
    for c in cards:
        ts = c.get("tracking_signal")
        if ts:
            symbols.update(_symbols_in_signal(ts))
        inv = c.get("invalidator") or {}
        args = inv.get("args") or {}
        for key in ("symbol", "numerator", "denominator"):
            if key in args and isinstance(args[key], str):
                symbols.add(args[key])

    snapshot: dict[str, Any] = {}
    for sym in sorted(symbols):
        if "/" in sym:
            num, den = sym.split("/", 1)
            try:
                points = await compute_ratio(numerator=num, denominator=den)
                if points:
                    snapshot[sym] = {
                        "latest": float(points[-1]["value"]),
                        "latest_ts": str(points[-1]["ts"]),
                        "points": len(points),
                    }
            except Exception as e:                  # noqa: BLE001
                logger.debug("compute_ratio failed for %s: %s", sym, e)
                continue
        else:
            row = (
                await session.execute(
                    select(MacroSeries.ts, MacroSeries.value)
                    .where(MacroSeries.symbol == sym)
                    .order_by(MacroSeries.ts.desc())
                    .limit(1)
                )
            ).first()
            if row is not None:
                snapshot[sym] = {
                    "latest": float(row[1]),
                    "latest_ts": str(row[0]),
                }
    return snapshot


def _symbols_in_signal(signal: str) -> list[str]:
    """tracking_signal can be 'AAPL', 'BTC-USD/GC=F', 'basket:BTC+MSTR'.
    Pull only what the macro store can serve."""
    if signal.startswith("basket:"):
        return []
    return [signal]


# ----- Accuracy snapshot ---------------------------------------------------

async def _accuracy_snapshot(
    session: AsyncSession, cards: list[dict[str, Any]]
) -> dict[str, Any]:
    """Per-ticker accuracy stats. Best-effort. We don't crash the bundle
    if the accuracy module schema differs across environments."""
    tickers: set[str] = set()
    for c in cards:
        for s in _symbols_in_signal(c.get("tracking_signal") or ""):
            if s and s.isupper() and "-" not in s and "/" not in s and "=" not in s:
                tickers.add(s)
        inv_args = (c.get("invalidator") or {}).get("args", {})
        sym = inv_args.get("symbol")
        if sym and isinstance(sym, str):
            if "/" not in sym and "=" not in sym and "-" not in sym:
                tickers.add(sym)

    if not tickers:
        return {}

    out: dict[str, Any] = {}
    try:
        from app.accuracy import service as acc_service  # type: ignore
    except Exception:                                # noqa: BLE001
        return {}

    for t in sorted(tickers):
        try:
            stats = await acc_service.snapshot_for_ticker(  # type: ignore[attr-defined]
                session, ticker=t, window_days=14,
            )
            if stats:
                out[t] = stats
        except Exception:                            # noqa: BLE001
            continue
    return out


# ----- Public entrypoint ---------------------------------------------------

async def build_bundle(
    *,
    query: str,
    hypothesis_slugs: Optional[list[str]] = None,
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    async with _db.SessionLocal() as session:
        cards = await _hypothesis_cards(session, hypothesis_slugs)
        evidence = await _retrieve_evidence(query, cards, k=k)
        macro = await _macro_snapshot(session, cards)
        accuracy = await _accuracy_snapshot(session, cards)

    bundle = {
        "query": query,
        "hypotheses": cards,
        "evidence": evidence,
        "macro_state": macro,
        "accuracy_snapshot": accuracy,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return _truncate(bundle, HARD_TOKEN_CAP)


# ----- Truncation ----------------------------------------------------------

def _truncate(bundle: dict, cap_tokens: int) -> dict:
    """Cheap word-count-as-token approximation. Drop oldest evaluations
    first, then trim excerpts by ascending score until under cap.

    Bounded by max_iterations to guarantee termination even on degenerate
    inputs (truncating an already-short excerpt that wouldn't change size).
    """
    max_iterations = 200
    for _ in range(max_iterations):
        if _approx_tokens(bundle) <= cap_tokens:
            break
        # Drop the oldest evaluation across all cards.
        dropped = False
        for card in bundle.get("hypotheses", []):
            evs = card.get("recent_evaluations") or []
            if len(evs) > 1:
                evs.pop()                          # last = oldest after sort-desc
                dropped = True
                break
        if dropped:
            continue
        # Then trim lowest-score excerpts.
        ev = bundle.get("evidence") or []
        if len(ev) > 3:
            ev.sort(key=lambda r: r.get("score", 0.0))
            ev.pop(0)
            bundle["evidence"] = sorted(ev, key=lambda r: r.get("score", 0.0), reverse=True)
            continue
        # Out of trim moves; truncate the longest excerpt body. Halve the
        # text on each pass to guarantee progress even when the floor is
        # non-zero.
        if ev:
            longest = max(ev, key=lambda r: len(r.get("text") or ""))
            txt = longest.get("text") or ""
            if len(txt) > 50:
                longest["text"] = txt[: max(50, len(txt) // 2)]
                continue
        break
    return bundle


def _approx_tokens(bundle: dict) -> int:
    """Approximate token count via word count + slight overhead."""
    import json as _json
    s = _json.dumps(bundle, default=str)
    return int(len(s.split()) * 1.3)
