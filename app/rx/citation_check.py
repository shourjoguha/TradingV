"""Citation verification (retrieval-depth-and-debiasing-program, Phase 2).

Deterministic, no-LLM check that a rec's quoted source spans actually appear in
the chunk they cite — the single highest-trust-per-line fix (council). Kills
limitation D1: a rec citing a real document with a quote the document does not
support. A fabricated/mis-attributed citation is the one error that instantly
destroys operator trust.

Pure functions only (no DB, no model, no I/O) so the logic is fully unit-
testable and can be called from BOTH the app ingest path and the Claude Code
commands that have chunk text in hand.

Verification is substring-after-normalization. Normalization is deliberately
forgiving of the artifacts that OCR + Whisper transcripts introduce (smart
quotes, dashes, collapsed whitespace, casing) so we flag genuine fabrication,
not formatting drift. Ellipsis-elided quotes ("<start> … <end>") are checked
fragment-by-fragment in order.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# A quote shorter than this (after normalization) can't be meaningfully
# verified — a 3-char fragment matches almost any chunk by accident, which
# would manufacture false confidence. Treated as UNVERIFIABLE, not verified.
_MIN_QUOTE_LEN = 12

# Ellipsis variants that signal an elided quote.
_ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…)\s*")

_WS_RE = re.compile(r"\s+")

# Smart punctuation → ASCII so a curly-quoted transcript matches a
# straight-quoted hand-typed quote and vice-versa.
_PUNCT_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ",
}


def _normalize(text: str) -> str:
    """Lowercase, fold smart punctuation, collapse whitespace, NFKC."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _PUNCT_MAP.items():
        text = text.replace(src, dst)
    text = text.lower()
    text = _WS_RE.sub(" ", text).strip()
    return text


def verify_quote(quote: Optional[str], chunk_text: Optional[str]) -> dict:
    """Verify a single quote against the chunk it claims to come from.

    Returns ``{"verified": bool, "reason": str}``. Reasons:
      * ``match``          — quote (or all ellipsis fragments, in order) found.
      * ``no_quote``       — nothing to verify (unverifiable, not a failure).
      * ``no_chunk_text``  — no source text supplied (unverifiable).
      * ``too_short``      — quote too short to verify safely (unverifiable).
      * ``not_found``      — quote NOT present → likely fabricated/mis-attributed.
    ``verified`` is True only on ``match``; every other reason is False.
    """
    if not quote or not quote.strip():
        return {"verified": False, "reason": "no_quote"}
    if not chunk_text or not chunk_text.strip():
        return {"verified": False, "reason": "no_chunk_text"}

    norm_chunk = _normalize(chunk_text)
    norm_quote = _normalize(quote)
    if len(norm_quote.replace(" ", "")) < _MIN_QUOTE_LEN:
        return {"verified": False, "reason": "too_short"}

    # Ellipsis-elided quote: require each fragment present, in order.
    fragments = [f for f in _ELLIPSIS_RE.split(norm_quote) if f.strip()]
    if len(fragments) > 1:
        cursor = 0
        for frag in fragments:
            idx = norm_chunk.find(frag, cursor)
            if idx == -1:
                return {"verified": False, "reason": "not_found"}
            cursor = idx + len(frag)
        return {"verified": True, "reason": "match"}

    if norm_quote in norm_chunk:
        return {"verified": True, "reason": "match"}
    return {"verified": False, "reason": "not_found"}


def annotate_source_refs(source_refs: object) -> object:
    """Annotate each source_ref dict in place-style with verification result.

    A ref may carry ``quote`` and (optionally) ``chunk_text`` / ``text``. The
    chunk text is what the quote is checked against; if absent the ref is
    UNVERIFIABLE (honest) rather than silently passing. Non-dict / non-list
    inputs are returned unchanged. Returns a NEW list (immutability).
    """
    if not isinstance(source_refs, list):
        return source_refs
    out = []
    for ref in source_refs:
        if not isinstance(ref, dict):
            out.append(ref)
            continue
        chunk_text = ref.get("chunk_text") or ref.get("text")
        result = verify_quote(ref.get("quote"), chunk_text)
        annotated = dict(ref)
        annotated["citation_verified"] = result["verified"]
        annotated["citation_reason"] = result["reason"]
        out.append(annotated)
    return out


# Reasons that mean "we couldn't check", vs a real pass/fail.
_UNVERIFIABLE_REASONS = {"no_quote", "no_chunk_text", "too_short"}


def status_from_refs(source_refs: object) -> str:
    """Derive a rec-level citation status from annotated source_refs.

    Returns one of:
      * ``no_quotes``   — no refs carried a checkable quote.
      * ``all_verified``— every checkable quote matched.
      * ``has_mismatch``— at least one quote was NOT found (the alarming case).
      * ``unverifiable``— quotes present but no chunk text to check against.
    Pure + idempotent: derivable on read from already-annotated refs OR from
    raw refs (it re-derives if annotations are missing).
    """
    if not isinstance(source_refs, list) or not source_refs:
        return "no_quotes"
    any_checkable = False
    any_mismatch = False
    any_verified = False
    any_unverifiable_with_quote = False
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        reason = ref.get("citation_reason")
        if reason is None:
            chunk_text = ref.get("chunk_text") or ref.get("text")
            reason = verify_quote(ref.get("quote"), chunk_text)["reason"]
        if reason == "match":
            any_checkable = True
            any_verified = True
        elif reason == "not_found":
            any_checkable = True
            any_mismatch = True
        elif reason in ("no_chunk_text", "too_short"):
            # A quote exists but we couldn't check it.
            if ref.get("quote"):
                any_unverifiable_with_quote = True
    if any_mismatch:
        return "has_mismatch"
    if any_verified:
        return "all_verified"
    if any_unverifiable_with_quote:
        return "unverifiable"
    return "no_quotes"
