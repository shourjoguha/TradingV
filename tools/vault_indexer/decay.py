"""Decay weighting — applied at retrieval, not at storage.

- Class A (books, notes, topics): weight = 1.0 (timeless).
- Class B (newsletters, videos): weight = exp(-age_months / (horizon/2)).
"""
from __future__ import annotations

import datetime
import math
from typing import Optional

from .config import CONFIG


def _today() -> datetime.date:
    return datetime.date.today()


def _months_since(iso_date: str) -> Optional[float]:
    try:
        d = datetime.date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    delta = _today() - d
    return delta.days / 30.0  # approximate months


def weight_for(node: dict) -> float:
    """Return retrieval weight in [0, 1] for a vault_node row dict."""
    horizon = node.get("horizon_months")
    if horizon is None or horizon == 0:
        return 1.0
    pub = node.get("published_at")
    if not pub:
        return 1.0
    age = _months_since(pub)
    if age is None or age <= 0:
        return 1.0
    half_life = horizon / 2.0
    return math.exp(-age / half_life)
