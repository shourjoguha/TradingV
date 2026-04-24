"""Canonical interval catalog.

Single source of truth for the intervals the platform understands. Providers
map canonical → provider-specific codes internally; callers only ever see
canonical strings.
"""
from __future__ import annotations

from typing import Tuple

# Ordered by duration — keeps UI dropdowns deterministic.
CANONICAL_INTERVALS: Tuple[str, ...] = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "1d",
    "1w",
)

# Minute duration of each canonical interval, for eligibility math.
_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1d": 60 * 24,
    "1w": 60 * 24 * 7,
}


def is_canonical(interval: str) -> bool:
    return interval in _MINUTES


def minutes(interval: str) -> int:
    return _MINUTES[interval]
