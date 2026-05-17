"""OCR-driven ticker auto-extraction for screenshot ingest.

When operator drops a chart screenshot, we OCR the image and look for
ticker-shaped tokens (1-5 uppercase letters) that are in the operator's
dynamic universe (roster ∪ boards ∪ The Street tier-1/2). Returns a
ranked list of candidates so the frontend can prefill the form. Operator
still confirms or corrects — this is a typing-reduction aid, not an
auto-submit.

Reuses ``tools.vault_indexer.ingest.chart_extractor.load_ticker_whitelist_sync``
for the whitelist, and the same stoplist as Stage 2 of the video-vision
chart-extraction chain (AI/USA/GDP/etc. filtered even when whitelist empty).

Failure contract: never raises. Returns ``{"candidates": [], "ocr_used": False}``
when pytesseract or PIL unavailable, image unreadable, or zero hits.
"""
from __future__ import annotations

import logging
import re
from io import BytesIO

from tools.vault_indexer.ingest.chart_extractor import (
    _DEFAULT_STOPLIST,
    _TICKER_TOKEN_RE,
    load_ticker_whitelist_sync,
)

logger = logging.getLogger(__name__)


# Chart-title regions tend to be top-left; this regex prefers tokens at
# start-of-line over scattered noise. Two passes — strict (early in OCR
# text) then loose (anywhere) — and dedupe preserving first-seen order.
_LINE_LEADING_RE = re.compile(r"^[\s\W]*([A-Z]{1,5})\b", re.MULTILINE)


def _ocr_image(image_bytes: bytes) -> str:
    """Return Tesseract OCR text on the image. Empty string on any failure."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        logger.warning("ticker_extract: missing pytesseract/PIL (%s)", e)
        return ""
    try:
        img = Image.open(BytesIO(image_bytes))
        # Upscale small images so tesseract has more pixels for chart axis text.
        if img.width < 1024:
            ratio = 1024 / float(img.width)
            new_size = (1024, max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.LANCZOS)
        return pytesseract.image_to_string(img) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("ticker_extract: OCR failed: %s", e)
        return ""


def extract_candidates(image_bytes: bytes, *, limit: int = 5) -> dict:
    """Return ``{"candidates": [...], "ocr_used": bool}``.

    ``candidates`` is a list of dicts ``{"ticker": str, "source": "whitelist" | "stoplist-passed"}``
    ranked by:
      1. Whitelist hits first (operator's known universe — high confidence)
      2. Within each group, line-leading hits before scattered hits
      3. Order of first appearance in OCR output

    Stoplist (AI/USA/GDP/etc.) ALWAYS filters even when whitelist empty.
    """
    text = _ocr_image(image_bytes)
    if not text:
        return {"candidates": [], "ocr_used": False}

    whitelist = load_ticker_whitelist_sync()
    stoplist = _DEFAULT_STOPLIST

    # Line-leading pass — high-precision (typical ticker is at chart-header top-left).
    leading: list[str] = []
    for m in _LINE_LEADING_RE.finditer(text):
        tok = m.group(1)
        if tok in stoplist:
            continue
        if tok not in leading:
            leading.append(tok)

    # Full-text pass — broader recall.
    full: list[str] = []
    for tok in _TICKER_TOKEN_RE.findall(text):
        if tok in stoplist:
            continue
        if tok not in full and tok not in leading:
            full.append(tok)

    candidates: list[dict] = []
    seen: set[str] = set()

    # Whitelist + leading
    for tok in leading:
        if tok in whitelist and tok not in seen:
            candidates.append({"ticker": tok, "source": "whitelist", "position": "leading"})
            seen.add(tok)

    # Whitelist + full-text
    for tok in full:
        if tok in whitelist and tok not in seen:
            candidates.append({"ticker": tok, "source": "whitelist", "position": "anywhere"})
            seen.add(tok)

    # Non-whitelist leading hits — kept as "stoplist-passed" so frontend
    # can show them with lower confidence (operator may confirm a new
    # ticker not yet on roster).
    for tok in leading:
        if tok not in seen:
            candidates.append({"ticker": tok, "source": "stoplist-passed", "position": "leading"})
            seen.add(tok)

    # Non-whitelist anywhere — lowest confidence, but operator can still pick.
    for tok in full:
        if tok not in seen:
            candidates.append({"ticker": tok, "source": "stoplist-passed", "position": "anywhere"})
            seen.add(tok)

    return {
        "candidates": candidates[:limit],
        "ocr_used": True,
    }
