"""Orchestrate ask: bundle → call → validate DSL → render md → persist."""
from __future__ import annotations

import datetime
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from app.core import db as _db
from app.hypotheses import invalidator as inv_dsl
from app.hypotheses import service as hyp_service
from app.research import bundle as _bundle
from app.research import client as _client
from app.research import models as _models
from app.research import prompts as _prompts
from app.research import rendering as _rendering

logger = logging.getLogger(__name__)


VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(Path.home() / "Documents" / "knowledge-vault")))
RESEARCH_FOLDER = "Research"


def _flatten_evidence(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in (bundle.get("evidence") or []):
        out.append({
            "vault_path": e.get("vault_path", ""),
            "title": e.get("title"),
            "section": e.get("section"),
            "text": (e.get("text") or "")[:600],
            "similarity": float(e.get("similarity", 0.0) or 0.0),
            "decay_weight": float(e.get("decay_weight", 1.0) or 1.0),
            "score": float(e.get("score", 0.0) or 0.0),
            "published_at": e.get("published_at"),
            "author": e.get("author"),
        })
    return out


def _flatten_macro(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sym, info in (bundle.get("macro_state") or {}).items():
        if isinstance(info, dict) and "latest" in info:
            out.append({
                "symbol": sym,
                "latest": float(info["latest"]),
                "latest_ts": str(info.get("latest_ts", "")),
            })
    return out


def _flatten_source_context(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Pass through operator-authored `_index.md` vignettes verbatim — no
    truncation by design."""
    out: list[dict[str, Any]] = []
    for s in (bundle.get("source_context") or []):
        out.append({
            "path": s.get("path", ""),
            "title": s.get("title"),
            "body": s.get("body") or "",
            "applies_to": list(s.get("applies_to") or []),
        })
    return out


TOOL_PROPOSE_INVALIDATOR_UPDATE = {
    "name": "propose_invalidator_update",
    "description": (
        "Propose tightening or loosening one hypothesis's invalidator DSL. "
        "The operator reviews + approves before any change is applied. "
        "Only call this when the bundle's evidence supports a concrete change. "
        "Use ONLY the operator's existing 5-op DSL: ratio_below_sma, "
        "series_above_threshold, series_below_threshold, series_change_pct, manual."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hypothesis_slug": {"type": "string"},
            "rationale": {"type": "string"},
            "proposed_invalidator": {
                "type": "object",
                "properties": {
                    "op": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["op", "args"],
            },
            "evidence_paths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "hypothesis_slug",
            "rationale",
            "proposed_invalidator",
            "confidence",
        ],
    },
}


def _validate_proposed(
    tool_call: dict[str, Any], bundle: dict[str, Any]
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Server-side checks on Claude's tool_use payload.

    Returns (validated_action, rejection_reason). Either field is set,
    never both.
    """
    if tool_call.get("name") != "propose_invalidator_update":
        return None, f"unexpected tool: {tool_call.get('name')}"
    payload = tool_call.get("input") or {}
    slug = payload.get("hypothesis_slug")
    if not slug:
        return None, "missing hypothesis_slug"

    bundled_slugs = {c["slug"] for c in bundle.get("hypotheses") or []}
    if slug not in bundled_slugs:
        return None, f"hypothesis_slug {slug} not in bundle"

    inv = payload.get("proposed_invalidator")
    try:
        inv_dsl.validate_spec(inv)
    except Exception as e:                              # noqa: BLE001
        return None, f"invalid DSL: {e}"

    bundled_paths = {ex["vault_path"] for ex in bundle.get("evidence") or []}
    paths = payload.get("evidence_paths") or []
    if any(p not in bundled_paths for p in paths):
        return None, "evidence_paths references content not in bundle"

    return payload, None


async def _check_tv_context(
    *, tickers: list[str], since_hours: int = 168
) -> list[dict[str, Any]]:
    """Per-ticker recent-context probe. Returns list of dicts shaped for
    ``TickerContextStatus``."""
    from app.tv_context import service as tvc_service

    out: list[dict[str, Any]] = []
    if not tickers:
        return out
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)
    async with _db.SessionLocal() as session:
        for raw in tickers:
            t = (raw or "").strip().upper()
            if not t:
                continue
            rows = await tvc_service.recent_for_ticker(
                session=session, ticker=t, since=since
            )
            most_recent = max((r.captured_at for r in rows), default=None)
            out.append({
                "ticker": t,
                "available_count": len(rows),
                "most_recent_at": most_recent,
                "needs_context": len(rows) == 0,
            })
    return out


async def ask(
    *,
    query: str,
    hypothesis_slugs: Optional[list[str]] = None,
    tickers: Optional[list[str]] = None,
    force_skip_context_gate: bool = False,
) -> dict[str, Any]:
    """Run a single stress-test query end-to-end. Returns a dict shaped
    for ``AskResponse``."""
    asked_at = datetime.datetime.now(datetime.timezone.utc)
    research_query_id = str(uuid.uuid4())

    bundle = await _bundle.build_bundle(query=query, hypothesis_slugs=hypothesis_slugs)
    bundle_text = _prompts.render_bundle_text(bundle)

    # Phase 4 gating. If any bundled hypothesis flagged requires_tv_context
    # AND operator supplied tickers AND any ticker has 0 recent items →
    # return early. Saves an LLM call + forces operator to attach context.
    context_check: list[dict[str, Any]] = []
    if tickers:
        context_check = await _check_tv_context(tickers=tickers)
    if not force_skip_context_gate:
        flagged = any(
            (h.get("requires_tv_context") or False)
            for h in (bundle.get("hypotheses") or [])
        )
        if flagged and any(c["needs_context"] for c in context_check):
            # Don't persist a research_queries row — gating is ephemeral
            # (no LLM call, no audit value). Re-submit with attached context
            # creates a fresh row.
            return {
                "query_id": research_query_id,
                "answer_path": None,
                "verdict": None,
                "tokens_in": 0,
                "tokens_out": 0,
                "est_cost_usd": 0.0,
                "proposed_action": None,
                "status": "needs_context",
                "evidence": _flatten_evidence(bundle),
                "macro_state": _flatten_macro(bundle),
                "source_context": _flatten_source_context(bundle),
                "context_check": context_check,
            }

    try:
        result = await _client.ask_claude(
            system=_prompts.SYSTEM_PROMPT,
            bundle_text=bundle_text,
            query=query,
            tools=[TOOL_PROPOSE_INVALIDATOR_UPDATE],
            one_shot_messages=_prompts.one_shot_messages(),
        )
    except Exception as e:                              # noqa: BLE001
        logger.exception("Claude call failed")
        await _persist_query(
            id_=research_query_id,
            query=query,
            hypothesis_ids=hypothesis_slugs or [],
            bundle=bundle,
            response={"error": str(e)},
            verdict=None,
            answer_path=None,
            tokens_in=0,
            tokens_out=0,
            est_cost_usd=0.0,
            status=_models.STATUS_ERROR,
            approved_action=None,
        )
        return {
            "query_id": research_query_id,
            "answer_path": None,
            "verdict": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "est_cost_usd": 0.0,
            "proposed_action": None,
            "status": _models.STATUS_ERROR,
            "evidence": _flatten_evidence(bundle),
            "macro_state": _flatten_macro(bundle),
            "source_context": _flatten_source_context(bundle),
            "context_check": context_check,
        }

    # Validate any tool call.
    proposed_action: Optional[dict[str, Any]] = None
    for call in result.tool_calls:
        validated, why_not = _validate_proposed(call, bundle)
        if validated:
            proposed_action = validated
            break
        logger.info("dropped tool call: %s", why_not)

    answer_path_rel = _write_markdown(
        query=query,
        bundle=bundle,
        verdict_text=result.verdict_text,
        proposed_action=proposed_action,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        est_cost_usd=result.est_cost_usd,
        research_query_id=research_query_id,
        asked_at=asked_at,
    )

    await _persist_query(
        id_=research_query_id,
        query=query,
        hypothesis_ids=hypothesis_slugs or [c["slug"] for c in bundle["hypotheses"]],
        bundle=bundle,
        response={
            "verdict_text": result.verdict_text,
            "tool_calls": result.tool_calls,
        },
        verdict=result.verdict_text[:300] if result.verdict_text else None,
        answer_path=answer_path_rel,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        est_cost_usd=float(result.est_cost_usd),
        status=_models.STATUS_PENDING,
        approved_action=None,
    )

    return {
        "query_id": research_query_id,
        "answer_path": answer_path_rel,
        "verdict": result.verdict_text,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "est_cost_usd": float(result.est_cost_usd),
        "proposed_action": proposed_action,
        "status": _models.STATUS_PENDING,
        "evidence": _flatten_evidence(bundle),
        "macro_state": _flatten_macro(bundle),
        "source_context": _flatten_source_context(bundle),
        "context_check": context_check,
    }


def _write_markdown(
    *,
    query: str,
    bundle: dict[str, Any],
    verdict_text: str,
    proposed_action: Optional[dict[str, Any]],
    tokens_in: int,
    tokens_out: int,
    est_cost_usd: float,
    research_query_id: str,
    asked_at: datetime.datetime,
) -> str:
    """Write the answer markdown into the vault and return the relative path."""
    cards = bundle.get("hypotheses") or []
    h_slug = (proposed_action or {}).get("hypothesis_slug") or (
        cards[0]["slug"] if cards else "answer"
    )
    filename = _rendering.answer_filename(h_slug, asked_at)
    rel_path = f"{RESEARCH_FOLDER}/{filename}"
    body = _rendering.render(
        query=query,
        bundle=bundle,
        verdict_text=verdict_text,
        proposed_action=proposed_action,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        est_cost_usd=est_cost_usd,
        research_query_id=research_query_id,
        asked_at=asked_at,
    )
    target = VAULT_PATH / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return rel_path


async def _persist_query(
    *,
    id_: str,
    query: str,
    hypothesis_ids: list[str],
    bundle: dict[str, Any],
    response: dict[str, Any],
    verdict: Optional[str],
    answer_path: Optional[str],
    tokens_in: int,
    tokens_out: int,
    est_cost_usd: float,
    status: str,
    approved_action: Optional[dict[str, Any]],
) -> None:
    async with _db.SessionLocal() as session:
        row = _models.ResearchQuery(
            id=id_,
            query=query,
            hypothesis_ids=hypothesis_ids,
            answer_path=answer_path,
            verdict=verdict,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            est_cost_usd=est_cost_usd,
            bundle=bundle,
            response=response,
            status=status,
            approved_action=approved_action,
        )
        session.add(row)
        await session.commit()


# ----- Approve / dismiss ---------------------------------------------------

async def approve(query_id: str) -> dict[str, Any]:
    """Apply the proposed action to its hypothesis. Idempotent."""
    async with _db.SessionLocal() as session:
        row = await session.get(_models.ResearchQuery, query_id)
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if row.status == _models.STATUS_APPROVED:
            return {"ok": True, "status": "already_approved"}
        if row.status != _models.STATUS_PENDING:
            return {"ok": False, "reason": f"status={row.status}"}

        # Re-extract the proposed action from response payload.
        tool_calls = (row.response or {}).get("tool_calls", [])
        proposed: Optional[dict[str, Any]] = None
        for tc in tool_calls:
            if tc.get("name") == "propose_invalidator_update":
                proposed = tc.get("input")
                break
        if proposed is None:
            return {"ok": False, "reason": "no proposed action"}

        # Defense in depth — re-validate.
        try:
            inv_dsl.validate_spec(proposed.get("proposed_invalidator"))
        except Exception as e:                          # noqa: BLE001
            return {"ok": False, "reason": f"invalid DSL: {e}"}

        slug = proposed["hypothesis_slug"]
        hyp = await hyp_service.get_by_slug(session, slug)
        if hyp is None:
            return {"ok": False, "reason": f"hypothesis not found: {slug}"}

        hyp.invalidator = proposed["proposed_invalidator"]
        row.status = _models.STATUS_APPROVED
        row.approved_at = datetime.datetime.now(datetime.timezone.utc)
        row.approved_action = proposed
        await session.commit()
        return {"ok": True, "status": "approved", "hypothesis_slug": slug}


async def dismiss(query_id: str) -> dict[str, Any]:
    async with _db.SessionLocal() as session:
        row = await session.get(_models.ResearchQuery, query_id)
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if row.status not in (_models.STATUS_PENDING, _models.STATUS_APPROVED):
            return {"ok": False, "reason": f"status={row.status}"}
        row.status = _models.STATUS_DISMISSED
        await session.commit()
        return {"ok": True}


async def delete(query_id: str) -> dict[str, Any]:
    """Hard-delete a research_queries row. Markdown archive in the vault is
    NOT touched — operator removes that manually if desired."""
    async with _db.SessionLocal() as session:
        row = await session.get(_models.ResearchQuery, query_id)
        if row is None:
            return {"ok": False, "reason": "not_found"}
        await session.delete(row)
        await session.commit()
        return {"ok": True}
