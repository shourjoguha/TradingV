"""Drift monitors — preference drift + embedding-distribution shift (Phase 6).

Two detectors the existing prediction-MAPE drift (`app/accuracy/drift.py`) does
NOT cover:

  * **Preference drift (B6)** — the operator's *taste* drifting, detected as a
    declining SLOPE in action_rate / subjective_fit over rolling windows. The
    MAPE detector sees the model's price predictions decay; it cannot see the
    operator quietly disengaging. action_rate alone is a lagging level; the
    slope catches the trend earlier.
  * **Embedding-distribution shift** — the incoming-content distribution
    drifting, detected as cosine distance between the rolling embedding
    centroid now vs a baseline. Flags when the corpus is being fed materially
    different material than the index was tuned on.

Pure functions (no DB, no model). The actual series + centroids are assembled
by the caller (an endpoint, a cron, or the operator) from the disposition log
and the indexer; these functions just do the math + thresholding so the logic
is unit-testable and identical everywhere.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence


def linear_slope(series: Sequence[float]) -> Optional[float]:
    """Least-squares slope of ``series`` over evenly-spaced x = 0..n-1.

    Returns None for <2 points (a slope needs at least two). Units are
    "value change per window".
    """
    n = len(series)
    if n < 2:
        return None
    xs = range(n)
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    return cov / var_x


def preference_drift(
    window_values: Sequence[float],
    *,
    slope_threshold: float = 0.05,
) -> dict:
    """Detect preference drift from a rolling series (e.g. per-week action_rate).

    ``slope_threshold`` is the magnitude (value/window) beyond which a trend is
    flagged. A negative slope past the threshold = **declining** (the alarming
    case: recs landing worse over time). Returns
    ``{slope, drifting, direction}`` where direction ∈
    declining | improving | stable | insufficient_data.
    """
    slope = linear_slope(window_values)
    if slope is None:
        return {"slope": None, "drifting": False, "direction": "insufficient_data"}
    if slope <= -abs(slope_threshold):
        return {"slope": slope, "drifting": True, "direction": "declining"}
    if slope >= abs(slope_threshold):
        return {"slope": slope, "drifting": True, "direction": "improving"}
    return {"slope": slope, "drifting": False, "direction": "stable"}


def _cosine(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    if len(a) != len(b) or not a:
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)


def embedding_centroid_shift(
    baseline_centroid: Sequence[float],
    current_centroid: Sequence[float],
    *,
    distance_threshold: float = 0.15,
) -> dict:
    """Cosine-distance shift between a baseline + current embedding centroid.

    ``distance = 1 - cosine_similarity`` ∈ [0, 2]. Flags ``shifted`` when the
    distance exceeds ``distance_threshold`` — the incoming-content distribution
    has moved materially from what the index was tuned on. Returns
    ``{distance, shifted}``; distance None when centroids are unusable
    (length mismatch / zero vector).
    """
    cos = _cosine(baseline_centroid, current_centroid)
    if cos is None:
        return {"distance": None, "shifted": False}
    distance = 1.0 - cos
    return {"distance": distance, "shifted": distance > distance_threshold}


def centroid(vectors: Sequence[Sequence[float]]) -> Optional[list[float]]:
    """Mean vector over a batch of embeddings. None for empty / ragged input."""
    if not vectors:
        return None
    dim = len(vectors[0])
    if dim == 0 or any(len(v) != dim for v in vectors):
        return None
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(dim)]
