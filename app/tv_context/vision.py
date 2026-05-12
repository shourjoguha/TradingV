"""Claude-vision summarizer for chart screenshots.

Default ON per operator preference: low typing-effort, accept ~$0.01/image
cost. Toggle per-upload + per-account default. Costs logged into
``tv_context_items.payload.vision`` and surfaced in the Inbox header.

The summary writes back into the screenshot's sidecar `.md` between
``<!-- vision-summary:start -->`` markers so the vault indexer picks it up
on the next reindex.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from io import BytesIO
from typing import Any

from app.core.config import SETTINGS

logger = logging.getLogger(__name__)


# Pricing mirrors app/research/client.py (Claude Sonnet 4.6 list).
def _f(env: str, default: float) -> float:
    v = os.environ.get(env)
    return float(v) if v is not None else default


def _input_per_mtok() -> float:
    return _f("CLAUDE_INPUT_COST_PER_MTOK", 3.00)


def _output_per_mtok() -> float:
    return _f("CLAUDE_OUTPUT_COST_PER_MTOK", 15.00)


def _calc_cost(tokens_in: int, tokens_out: int) -> float:
    return round(
        tokens_in * _input_per_mtok() / 1_000_000
        + tokens_out * _output_per_mtok() / 1_000_000,
        6,
    )


SYSTEM_PROMPT = (
    "You are a chart-reading assistant. Given a TradingView chart image, "
    "produce a concise structured summary. Strict rule: do NOT invent values "
    "you cannot read off the chart. If a number is illegible, write 'unclear' "
    "instead of guessing. Output exactly two sections in markdown:\n\n"
    "**Structured**\n"
    "- ticker: <as labeled, or unclear>\n"
    "- timeframe: <e.g. 1D / 4H / 15m, or unclear>\n"
    "- pattern: <one phrase, e.g. 'breakout from descending wedge', or 'no clear pattern'>\n"
    "- indicators_visible: <comma-list of named indicators visible>\n"
    "- key_levels: <list of S/R or trendline levels, with prices if legible>\n"
    "- sentiment: <bullish | bearish | neutral | unclear>\n\n"
    "**Notes**\n"
    "<2-4 sentences of plain-English context: what the chart appears to show, "
    "what would invalidate or confirm the apparent setup. Reference only what "
    "you can see on the image.>"
)


def _downscale_png(image_bytes: bytes, max_width: int) -> bytes:
    """Lossy resize to reduce vision-input tokens. Returns PNG bytes.

    Falls back to original bytes if Pillow isn't available or the image
    can't be decoded — ingest must never fail because vision pre-proc broke.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return image_bytes
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.width <= max_width:
            return image_bytes
        ratio = max_width / float(img.width)
        new_size = (max_width, max(1, int(img.height * ratio)))
        img = img.convert("RGB") if img.mode in ("RGBA", "P") else img
        img = img.resize(new_size, Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001
        logger.warning("vision: downscale failed (%s); using original", e)
        return image_bytes


async def summarize_chart(
    *,
    image_bytes: bytes,
    ticker: str,
    operator_note: str | None = None,
) -> dict[str, Any]:
    """Call Claude vision; return structured payload (or failure record).

    Always returns a dict — never raises — so ingest pipelines aren't
    blocked by network/API failures. Failure path: ``{"status":"failed",
    "error": "..."}``.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "skipped", "error": "ANTHROPIC_API_KEY not set"}

    # Cost-aware C3 + C4 + C5: kill-switch + monthly cap + vision toggle.
    from app.admin import service as _admin_svc

    if await _admin_svc.anthropic_kill_switch_active():
        return {
            "status": "skipped",
            "error": "anthropic_kill_switch_active",
        }
    vision_enabled = await _admin_svc.get_setting(
        "tv_context.vision_enabled_this_month", True
    )
    if not bool(vision_enabled):
        return {
            "status": "skipped",
            "error": "tv_context_vision_disabled_for_month",
        }

    max_w = SETTINGS.TV_CTX_VISION_MAX_WIDTH_PX
    image_bytes = _downscale_png(image_bytes, max_w)
    img_b64 = base64.b64encode(image_bytes).decode("ascii")

    prefix = f"Ticker context: {ticker.upper()}."
    if operator_note:
        prefix += f' Operator note: "{operator_note.strip()}"'

    try:
        # Run sync SDK in thread; matches the pattern used elsewhere in
        # this codebase (research/client.py).
        from anthropic import Anthropic

        def _call() -> Any:
            client = Anthropic(api_key=api_key)
            return client.messages.create(
                model=SETTINGS.TV_CTX_VISION_MODEL,
                max_tokens=600,
                temperature=0.2,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": img_b64,
                                },
                            },
                            {"type": "text", "text": prefix},
                        ],
                    }
                ],
            )

        resp = await asyncio.to_thread(_call)
    except Exception as e:  # noqa: BLE001
        logger.warning("vision: API call failed: %s", e)
        return {"status": "failed", "error": str(e)[:200]}

    summary_md = ""
    try:
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                summary_md += getattr(block, "text", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("vision: response parse failed: %s", e)

    usage = getattr(resp, "usage", None)
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    cost = _calc_cost(tokens_in, tokens_out)

    return {
        "status": "ok",
        "summary_md": summary_md.strip(),
        "model": SETTINGS.TV_CTX_VISION_MODEL,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "downscaled_to_px": max_w,
    }
