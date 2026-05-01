"""Auto-tag — Claude Haiku proposes 1-5 tags from the controlled vocabulary.

Cheap, cached, vocabulary-constrained. Operator approves via the review
queue; nothing lands on a note until ticked.
"""
from __future__ import annotations

import json
from typing import Optional

from .config import CONFIG


_PROMPT_TEMPLATE = """You tag a markdown note with the operator's controlled vocabulary.

Pick the 1–5 most-applicable tags from the VOCABULARY below. Use ONLY the
listed tags. If no tag fits, return an empty list. NEVER invent new tags.

VOCABULARY:
{vocab_block}

NOTE TITLE: {title}
NOTE BODY (truncated):
{body}

Return strict JSON: {{"tags": ["..."], "reasoning": "..."}}
"""


def _vocab_block(tags: dict[str, str]) -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in sorted(tags.items()))


def suggest(
    *,
    title: str,
    body: str,
    vocabulary: dict[str, str],
    max_body_chars: int = 8000,
) -> list[str]:
    """Return a list of suggested tag names.

    Returns [] on any failure — auto-tag is best-effort. Operator review
    queue still gets populated; missing suggestions just mean operator
    tags manually.
    """
    if not CONFIG.auto_tag_enabled or not CONFIG.anthropic_key:
        return []
    if not vocabulary:
        return []

    try:
        from anthropic import Anthropic
    except ImportError:
        return []

    body_trim = body[:max_body_chars]
    prompt = _PROMPT_TEMPLATE.format(
        vocab_block=_vocab_block(vocabulary),
        title=title or "(untitled)",
        body=body_trim,
    )

    try:
        client = Anthropic(api_key=CONFIG.anthropic_key)
        resp = client.messages.create(
            model=CONFIG.auto_tag_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in resp.content if hasattr(block, "text")
        )
    except Exception:                                   # noqa: BLE001
        return []

    # Best-effort JSON extraction.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    raw = payload.get("tags") or []
    if not isinstance(raw, list):
        return []
    valid = [t for t in raw if isinstance(t, str) and t in vocabulary]
    # Cap at 5.
    return valid[:5]
