"""Render a stress-test answer as the markdown the operator sees in
Obsidian's Research/ folder."""
from __future__ import annotations

import datetime
import json
from typing import Any, Optional


def _slug(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    while out and out[-1] == "-":
        out.pop()
    return "".join(out) or "answer"


def answer_filename(hypothesis_slug: str, asked_at: datetime.datetime) -> str:
    """Build a Research/<date>-<hslug>.md path component."""
    return f"{asked_at.date().isoformat()}-{_slug(hypothesis_slug)}.md"


def render(
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
    """Return the full markdown body (including frontmatter)."""
    cards = bundle.get("hypotheses") or []
    primary_slug = (proposed_action or {}).get("hypothesis_slug") or (
        cards[0]["slug"] if cards else "all"
    )
    primary_card = next(
        (c for c in cards if c["slug"] == primary_slug),
        cards[0] if cards else None,
    )

    lines: list[str] = []
    # Frontmatter
    lines.append("---")
    lines.append("kind: research_answer")
    title = (
        f"Stress-test: {primary_card['slug']}" if primary_card else f"Research — {asked_at.date().isoformat()}"
    )
    lines.append(f"title: {json.dumps(title)}")
    if primary_card:
        lines.append(f"hypothesis_slug: {primary_card['slug']}")
    lines.append(f"asked_at: {asked_at.isoformat()}")
    lines.append(f"research_query_id: {research_query_id}")
    lines.append("tags: [research]")
    lines.append("---")
    lines.append("")

    # Header
    if primary_card:
        lines.append(f"# Stress-test: {primary_card['slug']} — {asked_at.date().isoformat()}")
    else:
        lines.append(f"# Research — {asked_at.date().isoformat()}")
    lines.append("")
    lines.append(f"**Query:** {query}")
    lines.append("")
    lines.append("**Verdict:**")
    lines.append("")
    lines.append(verdict_text or "_(no verdict text returned)_")
    lines.append("")

    # Evidence
    evidence = bundle.get("evidence") or []
    if evidence:
        lines.append("## Evidence")
        lines.append("")
        for ex in evidence:
            score = ex.get("score") or 0.0
            lines.append(
                f"- [[{ex['vault_path']}]] — score {score:.2f}"
                + (f" · {ex.get('section')}" if ex.get("section") else "")
            )
        lines.append("")

    macro = bundle.get("macro_state") or {}
    if macro:
        lines.append("## Macro state")
        lines.append("")
        for symbol, info in macro.items():
            latest = info.get("latest")
            ts = info.get("latest_ts")
            if latest is not None and ts:
                lines.append(f"- `{symbol}`: {latest} (as of {ts})")
        lines.append("")

    # Proposed action
    if proposed_action:
        slug = proposed_action.get("hypothesis_slug")
        rationale = proposed_action.get("rationale", "")
        confidence = proposed_action.get("confidence", 0.0)
        invalidator = proposed_action.get("proposed_invalidator", {})
        lines.append("## Proposed action")
        lines.append("")
        lines.append(f"- [ ] **Approve:** update `{slug}` invalidator")
        lines.append(f"  - Op: `{invalidator.get('op')}`")
        lines.append(f"  - Args: `{json.dumps(invalidator.get('args') or {}, sort_keys=True)}`")
        lines.append(f"  - Rationale: {rationale}")
        lines.append(f"  - Confidence: {confidence}")
        lines.append("")
        lines.append(
            "Tick the box and save to apply. Indexer's next watch event "
            "will call `POST /v1/research/queries/{id}/approve` and the "
            "DSL will be patched onto the hypothesis row."
        )
        lines.append("")
    else:
        lines.append("## Proposed action")
        lines.append("")
        lines.append(
            "_None — the evidence does not support a concrete invalidator change._"
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"*tokens_in: {tokens_in} · tokens_out: {tokens_out} · "
        f"est_cost_usd: ${est_cost_usd:.4f}*"
    )
    lines.append("")
    return "\n".join(lines)
