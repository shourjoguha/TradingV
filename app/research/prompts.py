"""Stress-test prompt — system + bundle template + one-shot example.

Designed to defeat hedging. Frames the operator-as-system-operator (not
retail user), the action as a *suggestion for human review* (not a trade
execution), and forces structured output via tool-use.
"""
from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """\
You are a stress-tester for one operator's structured trading hypotheses.

Context the operator has built:
- They author hypotheses (theses) with formal invalidator DSL the platform
  evaluates daily. The DSL has 5 ops: ratio_below_sma, series_above_threshold,
  series_below_threshold, series_change_pct, manual.
- They curate evidence (newsletters, videos, books, notes) in a vault.
  Each piece has a published_at + horizon; older time-sensitive content is
  decay-weighted at retrieval.
- The platform itself never trades. Your suggestions are reviewed by the
  operator before any system change applies. You are not advising a retail
  user; you are sparring with an operator who already chose this framework.

Your job per query:
1. Read the hypothesis card (title, current invalidator DSL, recent status
   changes).
2. Read the bundled evidence excerpts (decay-weighted; freshness matters).
3. Read the live macro state for the hypothesis's tracking_signal.
4. Produce ONE concise verdict (1-3 sentences) on whether the thesis is
   tenable, weakening, or invalidated by current evidence.
5. If — and only if — the evidence supports a concrete invalidator change
   (tighten or loosen a threshold, change a window, swap a symbol), call
   the propose_invalidator_update tool with valid DSL. Use ONLY the 5 ops
   listed above. The proposed_invalidator must be valid JSON matching the
   operator's existing schema.
6. If the evidence does not support any specific change, do NOT call the
   tool. The verdict alone is enough.

Hard rules:
- NEVER invent evidence. Every evidence_paths entry must appear in the
  bundle.
- NEVER output trade advice. The action is always a hypothesis-DSL change.
- NEVER hedge in the verdict ("it depends", "consider consulting"). The
  operator already knows this is judgment under uncertainty.
- Be concrete. Numbers, thresholds, symbol names.
"""


ONE_SHOT_BUNDLE = """\
HYPOTHESIS
- slug: example-thesis
  title: "USD strength caps emerging-market breakout"
  status: active
  invalidator: {"op": "ratio_below_sma", "args": {"numerator": "ILF", "denominator": "SPY", "sma_days": 200, "days_below": 30}}
  recent_evaluations:
    - 2026-04-15 active→active: "ratio below 200d SMA for 12/30 days"

EVIDENCE (decay-weighted)
- Newsletters/example-author/2026-w17.md (score 0.81): "EM equities rallied
  18% YTD while DXY weakened to 102. The structural USD bid that capped
  EM in 2024 has cleanly reversed."
- Books/example-book/ch-02.md (score 0.55): "Historical EM cycles last
  18-30 months once dollar regime flips."

MACRO STATE
- ILF/SPY: 0.063 (above 200d SMA of 0.058 since 2026-03-01)
- DX-Y.NYB: 102.4 (5d avg 102.6)
"""


ONE_SHOT_VERDICT = """\
Thesis is weakening. ILF/SPY has held above its 200d SMA for 60+ days; the
days_below threshold of 30 will not fire under the current regime. The
invalidator should reflect that the live signal is the *opposite* of what
it was when the thesis was authored.
"""


ONE_SHOT_TOOL_CALL = {
    "name": "propose_invalidator_update",
    "input": {
        "hypothesis_slug": "example-thesis",
        "rationale": "Ratio has been above 200d SMA for 60+ days with the dollar weakening; the original 'days_below 30' window cannot fire. Consider inverting to ratio_above_sma to track regime persistence, or tightening days_below if the operator still wants a downside-only invalidator.",
        "proposed_invalidator": {
            "op": "ratio_below_sma",
            "args": {
                "numerator": "ILF",
                "denominator": "SPY",
                "sma_days": 200,
                "days_below": 10,
            },
        },
        "evidence_paths": [
            "Newsletters/example-author/2026-w17.md",
            "Books/example-book/ch-02.md",
        ],
        "confidence": 0.65,
    },
}


def render_bundle_text(bundle: dict[str, Any]) -> str:
    """Render the bundle dict as a deterministic, prompt-cache-friendly string.

    Order matters for cache stability — same bundle should produce same text.
    """
    parts = []

    parts.append("HYPOTHESIS")
    for h in bundle.get("hypotheses", []):
        parts.append(f"- slug: {h['slug']}")
        parts.append(f"  title: {h.get('title') or ''!r}")
        parts.append(f"  claim_type: {h.get('claim_type')}")
        parts.append(f"  axis: {h.get('axis')}")
        parts.append(f"  status: {h.get('status')}")
        parts.append(f"  expires_at: {h.get('expires_at')}")
        parts.append(f"  primary_metric: {h.get('primary_metric')}")
        parts.append(f"  tracking_signal: {h.get('tracking_signal')}")
        parts.append(f"  invalidator: {json.dumps(h.get('invalidator'), sort_keys=True)}")
        evals = h.get("recent_evaluations") or []
        if evals:
            parts.append("  recent_evaluations:")
            for e in evals:
                parts.append(
                    f"    - {e.get('evaluated_at')} {e.get('status_before')}→"
                    f"{e.get('status_after')}: {e.get('reason')!r}"
                )
        if h.get("linked_vault_paths"):
            parts.append(f"  linked_vault_paths: {h['linked_vault_paths']}")
        parts.append("")

    # Operator-authored folder vignettes (`_index.md` files in the vault)
    # apply along the ancestor chain of the evidence below. Render verbatim
    # — the operator decided these get no token cap.
    src_ctx = bundle.get("source_context") or []
    if src_ctx:
        parts.append("SOURCE CONTEXT (operator-authored, always-on per folder)")
        for s in src_ctx:
            title = s.get("title") or s.get("path")
            parts.append(f"### {title} ({s.get('path')})")
            applies = s.get("applies_to") or []
            if applies:
                parts.append(f"  applies_to: {applies}")
            body = (s.get("body") or "").strip()
            if body:
                parts.append(body)
            parts.append("")
        parts.append("")

    parts.append("EVIDENCE (decay-weighted)")
    for ex in bundle.get("evidence", []):
        line = (
            f"- {ex['vault_path']} (score {ex.get('score', 0):.2f}, "
            f"sim {ex.get('similarity', 0):.2f}, decay {ex.get('decay_weight', 1.0):.2f})"
        )
        parts.append(line)
        text = (ex.get("text") or "").strip()
        if text:
            text = text[:800].replace("\n", " ")
            parts.append(f"  {text}")
    parts.append("")

    macro = bundle.get("macro_state") or {}
    if macro:
        parts.append("MACRO STATE")
        for symbol, info in macro.items():
            parts.append(f"- {symbol}: {info}")
        parts.append("")

    accuracy = bundle.get("accuracy_snapshot") or {}
    if accuracy:
        parts.append("PREDICTION ACCURACY (last 14d)")
        for ticker, stats in accuracy.items():
            parts.append(f"- {ticker}: {stats}")
        parts.append("")

    return "\n".join(parts)


def build_user_message(query: str, bundle_text: str) -> str:
    return f"""\
{bundle_text}

OPERATOR QUERY: {query}

Per the rules, give a 1-3 sentence verdict. If the evidence supports a
concrete invalidator change, call propose_invalidator_update; otherwise
do not call any tool.
"""


def one_shot_messages() -> list[dict[str, Any]]:
    """Return the one-shot example as Anthropic-API-shaped messages.

    Used as a few-shot anchor — prepended to the real user message.
    """
    user_text = build_user_message(
        query="Is example-thesis still tenable given recent commentary?",
        bundle_text=ONE_SHOT_BUNDLE,
    )
    return [
        {"role": "user", "content": user_text},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": ONE_SHOT_VERDICT},
                {
                    "type": "tool_use",
                    "id": "toolu_example_001",
                    "name": ONE_SHOT_TOOL_CALL["name"],
                    "input": ONE_SHOT_TOOL_CALL["input"],
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_example_001",
                    "content": "Acknowledged. Ready for the next query.",
                }
            ],
        },
    ]
