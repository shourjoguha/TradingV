"""Deterministic keyword matcher over the canned answer library.

No LLM. No outbound HTTP. Pure-CPU lookup. If the user query overlaps
an answer's keyword set, return that answer. Otherwise return three
nearest-by-shared-keyword suggestions so the frontend renders pills
rather than an empty state.
"""
from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def match_query(q: str, canned: dict[str, Any]) -> dict[str, Any]:
    q_tokens = _tokens(q)
    presets = canned.get("presets", [])
    fallback_suggestions = [
        {"id": p["id"], "label": p["label"]} for p in presets[:3]
    ]
    if not q_tokens:
        return {"match": "miss", "answer_id": None, "suggestions": fallback_suggestions}

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in canned.get("answers", []):
        kw = {k.lower() for k in entry.get("keywords", [])}
        score = len(q_tokens & kw)
        if score:
            scored.append((score, entry))

    if not scored:
        return {"match": "miss", "answer_id": None, "suggestions": fallback_suggestions}

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    match_kind = "exact" if best_score >= 2 else "fuzzy"
    suggestions = [{"id": e["id"], "label": e["title"]} for _, e in scored[1:4]]
    return {"match": match_kind, "answer_id": best["id"], "suggestions": suggestions}
