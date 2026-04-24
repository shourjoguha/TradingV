"""Kronos eligibility validator — the single choke-point before inference.

Call `EligibilityValidator.check(...)` BEFORE every `adapter.predict(...)`.
Never bypass. All failure paths return `Ineligible` with a structured reason
so the caller can surface it verbatim to the user.
"""
from __future__ import annotations

from typing import Iterable

from .registry import ModelSpec, get_model, load_models
from .schemas import Eligible, EligibilityResult, Ineligible, IneligibleReason


class EligibilityValidator:
    @staticmethod
    def check(
        *,
        model_id: str,
        asset_class: str,
        interval: str,
        available_bars: int,
        available_features: Iterable[str],
        horizon_bars: int | None = None,
    ) -> EligibilityResult:
        spec = get_model(model_id)
        if spec is None:
            return Ineligible(
                reason=IneligibleReason.UNKNOWN_MODEL,
                message=f"model '{model_id}' is not registered",
            )

        if interval not in spec.supported_intervals:
            return Ineligible(
                reason=IneligibleReason.UNSUPPORTED_INTERVAL,
                message=(
                    f"model '{spec.id}' does not support interval '{interval}'. "
                    f"Supported: {list(spec.supported_intervals)}"
                ),
            )

        if asset_class not in spec.supported_asset_classes:
            return Ineligible(
                reason=IneligibleReason.UNSUPPORTED_ASSET,
                message=(
                    f"model '{spec.id}' does not support asset class '{asset_class}'. "
                    f"Supported: {list(spec.supported_asset_classes)}"
                ),
            )

        available = {f.lower() for f in available_features}
        missing = [f for f in spec.required_features if f.lower() not in available]
        if missing:
            return Ineligible(
                reason=IneligibleReason.MISSING_FEATURES,
                message=f"model '{spec.id}' requires features {missing}",
            )

        if available_bars < spec.min_history_bars:
            return Ineligible(
                reason=IneligibleReason.INSUFFICIENT_HISTORY,
                message=(
                    f"model '{spec.id}' needs at least {spec.min_history_bars} bars; "
                    f"got {available_bars}"
                ),
            )

        resolved_horizon = horizon_bars if horizon_bars is not None else spec.default_horizon_bars
        if resolved_horizon < 1 or resolved_horizon > spec.max_horizon_bars:
            return Ineligible(
                reason=IneligibleReason.HORIZON_OUT_OF_RANGE,
                message=(
                    f"model '{spec.id}' horizon must be in [1, {spec.max_horizon_bars}]; "
                    f"got {resolved_horizon}"
                ),
            )

        return Eligible(
            model_id=spec.id,
            horizon_bars=resolved_horizon,
            context_length=spec.context_length,
            unverified=spec.unverified,
        )


def eligible_models_for(
    *, asset_class: str, interval: str, available_bars: int | None = None
) -> list[ModelSpec]:
    """Filter registered models by asset/interval (and history, if provided).

    Used by `/v1/models` and `/v1/timeframes` to avoid surfacing combos that
    the validator would reject.
    """
    out: list[ModelSpec] = []
    for spec in load_models():
        if interval not in spec.supported_intervals:
            continue
        if asset_class not in spec.supported_asset_classes:
            continue
        if available_bars is not None and available_bars < spec.min_history_bars:
            continue
        out.append(spec)
    return out
