"""Extractive summarisation — pick the K sentences from a chunk that
best match a query.

Reuses the already-loaded ``BAAI/bge-large-en-v1.5`` encoder so there's
no second model in memory. Result is verbatim (no rewriting) — sentences
come straight out of the source. Suitable for surfacing a 1-3 sentence
preview of a 600-token vault chunk in the frontend's ``VaultChunkList``.

Algorithm:
    1. Split the chunk into sentences (regex on ``.!?`` followed by
       whitespace + uppercase, with a few empirical guards for common
       abbreviations like ``Mr.``, ``e.g.``, ``U.S.``).
    2. Encode each sentence as a passage; encode the query with the
       BGE query-side prefix.
    3. Cosine score (vectors are L2-normalised first to make dot-product
       valid), descending.
    4. Return the top ``k``, restored to **original order** so the
       narrative still reads forward, not by relevance.

For chunks shorter than ``k`` sentences the selector returns every
sentence. For chunks with no detectable sentence boundary it returns
the chunk truncated to ``fallback_chars`` characters.
"""
from __future__ import annotations

import math
import re
from typing import Sequence

from . import embed as _embed


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

# Common abbreviations that end with a period but should NOT close a
# sentence. Lowercased + period intentionally excluded from match (we
# strip it on lookup).
_ABBREVIATIONS = frozenset(
    [
        "mr",
        "mrs",
        "ms",
        "dr",
        "st",
        "jr",
        "sr",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "u.s",
        "u.k",
        "fig",
        "no",
        "vol",
        "approx",
        "inc",
        "ltd",
        "co",
        "corp",
        "p.s",
    ]
)

# Boundary candidate: terminator (.!?), then whitespace, then capital
# letter or digit-starting token.
_BOUNDARY = re.compile(r"([.!?])(\s+)(?=[A-Z0-9$])")


def _is_abbrev(left_token: str) -> bool:
    """True if the token immediately before a candidate boundary is a
    known abbreviation (so the period doesn't close a sentence)."""
    last = left_token.strip().rsplit(maxsplit=1)
    tail = last[-1] if last else left_token
    tail = tail.lower().rstrip(".")
    return tail in _ABBREVIATIONS


_PUNCT_ONLY = re.compile(r"^[\s.!?,;:\-—–]+$")
# Trailing orphan punctuation separated by whitespace from the last word —
# e.g. "Second sentence here. ." → strip the dangling " .". Doesn't touch
# punctuation glued directly to the last word ("here.").
_TRAILING_ORPHAN = re.compile(r"\s+[.!?,;:\-—–]+\s*$")


def split_sentences(text: str) -> list[str]:
    """Return a list of sentences. Whitespace-collapsed, no empty entries.

    Conservative on abbreviations — better to leave two clauses joined
    than to split mid-name. Caller should not depend on perfect
    grammatical sentences.
    """
    if not text:
        return []
    # Normalise whitespace so the regex sees consistent spaces.
    body = re.sub(r"\s+", " ", text).strip()
    if not body:
        return []

    out: list[str] = []
    last_end = 0
    for m in _BOUNDARY.finditer(body):
        boundary_idx = m.start()
        left = body[last_end : boundary_idx + 1]
        if _is_abbrev(left):
            continue
        out.append(body[last_end : boundary_idx + 1].strip())
        last_end = m.end()
    tail = body[last_end:].strip()
    if tail:
        out.append(tail)

    # Strip orphan trailing punctuation (e.g. " .") then drop fragments
    # under 3 chars OR consisting entirely of punctuation (trailing lone
    # "." after a real sentence is the common cause).
    cleaned = [_TRAILING_ORPHAN.sub("", s).rstrip() for s in out]
    return [s for s in cleaned if len(s) >= 3 and not _PUNCT_ONLY.match(s)]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _normalise(vec: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def select_top_sentences(
    query: str,
    text: str,
    *,
    k: int = 2,
    min_chars: int = 12,
    fallback_chars: int = 280,
) -> list[str]:
    """Return up to ``k`` sentences most relevant to ``query``, preserving
    their original order in ``text``.

    Behaviour:
        * Returns at most ``k`` sentences (typically 2 for a card teaser).
        * If the chunk has fewer than ``k`` sentences, returns all of
          them in order.
        * If the splitter produces nothing, returns
          ``[text[:fallback_chars]]`` so the UI always has something
          to render.
        * Sentences shorter than ``min_chars`` are filtered after
          splitting (avoid "OK." dominating the output).
    """
    sentences = [s for s in split_sentences(text) if len(s) >= min_chars]
    if not sentences:
        snippet = text.strip()
        return [snippet[:fallback_chars]] if snippet else []
    # If the chunk has no real sentence boundaries (the splitter returned
    # a single long blob), the user-facing teaser should still be short.
    if len(sentences) == 1 and len(sentences[0]) > fallback_chars:
        return [sentences[0][:fallback_chars]]
    if len(sentences) <= k:
        return sentences

    qvec = _normalise(_embed.encode_query(query))
    svecs = [_normalise(v) for v in _embed.encode_passages(sentences)]
    scored = sorted(
        ((i, _dot(qvec, v)) for i, v in enumerate(svecs)),
        key=lambda t: t[1],
        reverse=True,
    )
    keep_indices = sorted(idx for idx, _ in scored[:k])
    return [sentences[i] for i in keep_indices]
