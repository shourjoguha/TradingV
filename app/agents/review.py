"""Buy-review augmentation for the Agents lane.

TradingAgents emits a discrete BUY/SELL/HOLD plus a prose ``rationale_md`` — it
does NOT quantify a forward risk/reward. The operator's review flow wants, per
ticker: a buy-level call and a **6–12 month downside/upside** with the case
behind each. This module turns the debate narrative into that structured shape.

Design mirrors the rest of the lane (``adapter.py`` / ``real_engine.py``):
- the LLM extraction reuses the same Anthropic binding the engine already uses
  (``AGENTS_QUICK_MODEL`` → ``CLAUDE_MODEL``), imported lazily so the base app
  and the test suite never pay for langchain-anthropic;
- if that binding isn't available (no key, extras not installed, or a parse
  failure), we fall back to a deterministic, network-free heuristic and tag the
  result ``source="heuristic"`` rather than fabricating precise numbers.

The structured review is stored on the existing ``agent_decisions.meta`` JSON
column (``meta["review"]``) — no schema change.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

HORIZON = "6-12mo"

# Buy-level buckets, worst → best. The heuristic maps stance → bucket; the LLM
# path is asked to pick from this same vocabulary so the dashboard can render a
# consistent rating scale.
BUY_LEVELS = ("avoid", "rich", "fair", "attractive", "compelling")

_EXTRACTION_SYSTEM = (
    "You are a risk manager summarizing an equity trading-desk debate into a "
    "compact, structured risk/reward read. Respond with ONLY a JSON object, no "
    "prose, no markdown fences."
)


def _extraction_prompt(ticker: str, stance: str, rationale: str) -> str:
    return (
        f"Ticker: {ticker}\n"
        f"Desk stance: {stance}\n"
        f"Debate / rationale:\n{rationale or '(none provided)'}\n\n"
        "From the material above, produce a JSON object with exactly these keys:\n"
        '  "buy_level": one of ' + ", ".join(f'"{b}"' for b in BUY_LEVELS) + " "
        "(how attractive the current entry is);\n"
        '  "downside_pct": a negative number, the approximate % drawdown in a bear '
        "case over the next 6-12 months;\n"
        '  "downside_case": one sentence naming what drives that downside;\n'
        '  "upside_pct": a positive number, the approximate % gain in a bull case '
        "over the next 6-12 months;\n"
        '  "upside_case": one sentence naming what drives that upside;\n'
        '  "key_risks": array of up to 3 short strings;\n'
        '  "catalysts": array of up to 3 short strings.\n'
        "Base every number on the debate; do not invent unrelated facts. "
        "Return only the JSON object."
    )


def _resolve_model() -> str:
    return (
        os.environ.get("AGENTS_QUICK_MODEL")
        or os.environ.get("CLAUDE_MODEL")
        or "claude-sonnet-4-6"
    )


def _extract_review_llm(ticker: str, stance: str, rationale: str) -> dict[str, Any]:
    """Ask the configured Claude model to structure the debate. Raises on any
    failure so the caller can fall back to the heuristic."""
    # Lazy import: only paid for when the augmentation actually runs against a
    # real model (laptop path with requirements-agents.txt installed).
    from langchain_anthropic import ChatAnthropic  # type: ignore

    llm = ChatAnthropic(model=_resolve_model(), temperature=0, max_tokens=1024)
    msg = llm.invoke(
        [
            ("system", _EXTRACTION_SYSTEM),
            ("human", _extraction_prompt(ticker, stance, rationale)),
        ]
    )
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    return _coerce_review(_parse_json_object(text))


def _parse_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response (tolerates fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def _as_float(val: object, default: float) -> float:
    try:
        if isinstance(val, str):
            val = val.replace("%", "").strip()
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_str_list(val: object, limit: int = 3) -> list[str]:
    if isinstance(val, str):
        val = [val]
    if not isinstance(val, (list, tuple)):
        return []
    return [str(x).strip() for x in val if str(x).strip()][:limit]


def _coerce_review(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize whatever the model returned into the canonical review shape."""
    level = str(raw.get("buy_level", "")).strip().lower()
    if level not in BUY_LEVELS:
        level = "fair"
    down = -abs(_as_float(raw.get("downside_pct"), 0.0))
    up = abs(_as_float(raw.get("upside_pct"), 0.0))
    return {
        "horizon": HORIZON,
        "buy_level": level,
        "downside_pct": round(down, 1),
        "downside_case": str(raw.get("downside_case", "")).strip() or None,
        "upside_pct": round(up, 1),
        "upside_case": str(raw.get("upside_case", "")).strip() or None,
        "key_risks": _as_str_list(raw.get("key_risks")),
        "catalysts": _as_str_list(raw.get("catalysts")),
        "source": "llm",
    }


def _heuristic_review(stance: str, rationale: str) -> dict[str, Any]:
    """Deterministic, network-free fallback. Deliberately neutral — it encodes
    the stance's directional lean, NOT a fabricated price target, and is tagged
    ``source="heuristic"`` so downstream copy can flag it as un-quantified."""
    stance = (stance or "HOLD").upper()
    # Symmetric-ish placeholders skewed by the desk's directional call. These are
    # sentinels, not forecasts (see source tag).
    if stance == "BUY":
        level, down, up = "attractive", -15.0, 25.0
    elif stance == "SELL":
        level, down, up = "rich", -25.0, 10.0
    else:
        level, down, up = "fair", -18.0, 18.0
    snippet = (rationale or "").strip().splitlines()
    lead = snippet[0].strip() if snippet else ""
    return {
        "horizon": HORIZON,
        "buy_level": level,
        "downside_pct": down,
        "downside_case": (lead[:180] or None) if stance != "BUY" else None,
        "upside_pct": up,
        "upside_case": (lead[:180] or None) if stance == "BUY" else None,
        "key_risks": [],
        "catalysts": [],
        "source": "heuristic",
    }


def augment_decision(
    decision: dict[str, Any], *, allow_llm: Optional[bool] = None
) -> dict[str, Any]:
    """Return a structured 6–12mo review for one persisted decision dict.

    ``decision`` is the serialized ``AgentDecision`` (as returned by
    ``service.run_for_ticker``): needs ``ticker``, ``stance``, ``rationale_md``.

    ``allow_llm`` gates the paid extraction. Default: attempt the LLM only when
    the lane is enabled (``AGENTS_ENABLED``) — otherwise use the heuristic so
    stub / sandbox runs stay deterministic and offline. Any LLM failure falls
    back to the heuristic rather than raising.
    """
    ticker = str(decision.get("ticker", "")).upper()
    stance = str(decision.get("stance", "HOLD")).upper()
    rationale = str(decision.get("rationale_md") or "")

    if allow_llm is None:
        allow_llm = os.environ.get("AGENTS_ENABLED", "").lower() in ("1", "true", "yes")

    if allow_llm:
        try:
            return _extract_review_llm(ticker, stance, rationale)
        except Exception as e:  # noqa: BLE001 — degrade, never abort a batch
            logger.warning("agents.review: LLM extraction failed for %s (%s); "
                           "falling back to heuristic", ticker, e)
    return _heuristic_review(stance, rationale)
