"""Anthropic SDK wrapper. Single call per /research/ask. Prompt-cached
on the system prompt + bundle prefix; returns parsed verdict + tool
calls + token usage + USD cost."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ClaudeResult:
    verdict_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read_tokens: int = 0
    est_cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


# Defaults reflect Claude Sonnet 4.6 list pricing (USD per 1M tokens).
# Override via env if pricing changes or if a different model is used.
def _f(env: str, default: float) -> float:
    v = os.environ.get(env)
    return float(v) if v is not None else default


CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
INPUT_PER_MTOK = lambda: _f("CLAUDE_INPUT_COST_PER_MTOK", 3.00)
OUTPUT_PER_MTOK = lambda: _f("CLAUDE_OUTPUT_COST_PER_MTOK", 15.00)
CACHE_READ_PER_MTOK = lambda: _f("CLAUDE_CACHE_READ_COST_PER_MTOK", 0.30)


def _calc_cost(tokens_in: int, tokens_out: int, cache_read: int) -> float:
    return round(
        (tokens_in - cache_read) * INPUT_PER_MTOK() / 1_000_000
        + cache_read * CACHE_READ_PER_MTOK() / 1_000_000
        + tokens_out * OUTPUT_PER_MTOK() / 1_000_000,
        6,
    )


async def ask_claude(
    *,
    system: str,
    bundle_text: str,
    query: str,
    tools: list[dict[str, Any]],
    one_shot_messages: Optional[list[dict[str, Any]]] = None,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    api_key: Optional[str] = None,
) -> ClaudeResult:
    """Make a single Anthropic call. Returns parsed result.

    Cache hint: the system message and the bundle prefix in the user
    turn are stable across queries for the same hypothesis. SDK
    cache_control on those fields halves cost on repeat queries.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    from anthropic import Anthropic

    from app.research.prompts import build_user_message

    client = Anthropic(api_key=api_key)
    user_text = build_user_message(query, bundle_text)

    messages: list[dict[str, Any]] = []
    if one_shot_messages:
        messages.extend(one_shot_messages)
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": user_text,
                # Cache the bundle prefix; query line at the bottom changes.
                "cache_control": {"type": "ephemeral"},
            }
        ],
    })

    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=tools,
        messages=messages,
    )

    verdict_text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            verdict_text_parts.append(block.text)
        elif getattr(block, "type", None) == "tool_use":
            tool_calls.append(
                {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )

    usage = getattr(resp, "usage", None)
    tokens_in = getattr(usage, "input_tokens", 0) if usage else 0
    tokens_out = getattr(usage, "output_tokens", 0) if usage else 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    return ClaudeResult(
        verdict_text="\n".join(verdict_text_parts).strip(),
        tool_calls=tool_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cache_read_tokens=cache_read,
        est_cost_usd=_calc_cost(tokens_in, tokens_out, cache_read),
        raw=resp.model_dump() if hasattr(resp, "model_dump") else {},
    )
