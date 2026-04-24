"""Kronos service helpers.

Thin glue between the eligibility validator and the rest of the app.
Keeps feature-list constants in one place so routes and future orchestrator
(Phase 4) agree on what the OHLCV cache actually provides.
"""
from __future__ import annotations

from typing import Tuple

# Features the OHLCV cache stores natively.
# `amount` is nullable in cache; when a model requires it the adapter must
# backfill via `close * volume` before inference. The validator only checks
# that the feature column EXISTS here, not that every bar has it populated.
CACHE_FEATURES: Tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)
