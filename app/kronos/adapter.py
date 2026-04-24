"""Kronos adapter — interface + stub.

The adapter isolates every caller from the real Kronos implementation.
Phase 3 ships a stub that REFUSES to produce fake predictions; once the
upstream Kronos repo is integrated (Phase 5), the stub is swapped for a
concrete adapter that loads weights and runs inference.

Invariant: `predict()` accepts only `Eligible`. Do not widen this signature.
The validator is the choke-point; the adapter is the enforcement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .schemas import Eligible


class ConstraintSpecMissingError(RuntimeError):
    """Raised when a model's constraints are ambiguous at runtime."""


@dataclass(frozen=True)
class PredictionResult:
    model_id: str
    horizon_bars: int
    # Forecast payload is intentionally loose until the real adapter lands.
    forecast: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class KronosAdapter(Protocol):
    def predict(self, eligible: Eligible, ohlcv: Any) -> PredictionResult: ...


class StubAdapter:
    """Default adapter. Refuses to predict — Kronos not wired yet.

    If `settings.DEBUG_STUB` is true, returns a deterministic synthetic
    result so the orchestrator (Phase 4) can be exercised end-to-end without
    the real model. NEVER enable DEBUG_STUB in production.
    """

    def predict(self, eligible: Eligible, ohlcv: Any) -> PredictionResult:
        if not isinstance(eligible, Eligible):
            # Defensive: the validator's choke-point must run first.
            raise TypeError("StubAdapter.predict requires an Eligible instance")
        from app.core.config import SETTINGS

        if SETTINGS.DEBUG_STUB:
            return PredictionResult(
                model_id=eligible.model_id,
                horizon_bars=eligible.horizon_bars,
                forecast=[
                    {"step": i + 1, "close": 0.0} for i in range(eligible.horizon_bars)
                ],
                meta={"stub": True, "unverified": eligible.unverified},
            )
        raise NotImplementedError(
            "Kronos adapter not integrated yet. "
            "Phase 5 will wire the real model; Phase 3 only validates."
        )


_adapter: KronosAdapter = StubAdapter()


def get_adapter() -> KronosAdapter:
    return _adapter


def set_adapter(adapter: KronosAdapter) -> None:
    """Test / integration hook — swap the active adapter."""
    global _adapter
    _adapter = adapter
