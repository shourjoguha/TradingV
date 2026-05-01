"""Embedder — sentence-transformers loading bge-large from the HF cache.

bge-large recommends a query-side prefix; passages are encoded raw.
Vectors returned NOT pre-normalized; cosine distance via sqlite-vec
handles the rest.
"""
from __future__ import annotations

from typing import Sequence

from sentence_transformers import SentenceTransformer

from .config import CONFIG


_MODEL: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(CONFIG.embedding_model)
    return _MODEL


def encode_passages(texts: Sequence[str]) -> list[list[float]]:
    """Encode a batch of passages. Returns list of float lists."""
    if not texts:
        return []
    m = get_model()
    arr = m.encode(list(texts), show_progress_bar=False, convert_to_numpy=True)
    return [vec.tolist() for vec in arr]


def encode_query(query: str) -> list[float]:
    """Encode a single query. Applies the bge query-side prefix."""
    m = get_model()
    text = CONFIG.query_prefix + query
    arr = m.encode([text], show_progress_bar=False, convert_to_numpy=True)
    return arr[0].tolist()
