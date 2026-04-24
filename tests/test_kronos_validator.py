"""Unit tests for the Kronos eligibility validator.

Guardrail invariant: every rejection path returns a structured Ineligible
with a stable reason enum. These tests lock the invariant down.
"""
from __future__ import annotations

import pytest

from app.kronos.adapter import StubAdapter
from app.kronos.registry import get_model, load_models
from app.kronos.schemas import Eligible, Ineligible, IneligibleReason
from app.kronos.validator import EligibilityValidator, eligible_models_for

FEATURES = ("open", "high", "low", "close", "volume", "amount")


def _happy_path_args(model_id: str = "kronos_base") -> dict:
    spec = get_model(model_id)
    assert spec is not None
    return dict(
        model_id=spec.id,
        asset_class=spec.supported_asset_classes[0],
        interval=spec.supported_intervals[0],
        available_bars=spec.min_history_bars,
        available_features=FEATURES,
    )


def test_registry_loads_known_models():
    ids = {m.id for m in load_models()}
    assert {"kronos_base", "kronos_small", "kronos_mini"}.issubset(ids)


def test_eligible_on_happy_path():
    result = EligibilityValidator.check(**_happy_path_args())
    assert isinstance(result, Eligible)
    assert result.model_id == "kronos_base"
    assert result.horizon_bars > 0


def test_unknown_model():
    args = _happy_path_args()
    args["model_id"] = "kronos_vapor"
    result = EligibilityValidator.check(**args)
    assert isinstance(result, Ineligible)
    assert result.reason == IneligibleReason.UNKNOWN_MODEL


def test_unsupported_interval():
    args = _happy_path_args()
    args["interval"] = "1m"  # seed registry does not include 1m
    result = EligibilityValidator.check(**args)
    assert isinstance(result, Ineligible)
    assert result.reason == IneligibleReason.UNSUPPORTED_INTERVAL


def test_unsupported_asset():
    args = _happy_path_args()
    args["asset_class"] = "forex"
    result = EligibilityValidator.check(**args)
    assert isinstance(result, Ineligible)
    assert result.reason == IneligibleReason.UNSUPPORTED_ASSET


def test_missing_features():
    args = _happy_path_args()
    # Required is OHLC (volume/amount optional per Kronos code). Drop `close`
    # to trigger MISSING_FEATURES.
    args["available_features"] = ("open", "high", "low")
    result = EligibilityValidator.check(**args)
    assert isinstance(result, Ineligible)
    assert result.reason == IneligibleReason.MISSING_FEATURES


def test_insufficient_history():
    args = _happy_path_args()
    args["available_bars"] = 10
    result = EligibilityValidator.check(**args)
    assert isinstance(result, Ineligible)
    assert result.reason == IneligibleReason.INSUFFICIENT_HISTORY


def test_horizon_out_of_range():
    args = _happy_path_args()
    args["horizon_bars"] = 10_000
    result = EligibilityValidator.check(**args)
    assert isinstance(result, Ineligible)
    assert result.reason == IneligibleReason.HORIZON_OUT_OF_RANGE


def test_stub_adapter_refuses_ineligible_type():
    adapter = StubAdapter()
    with pytest.raises(TypeError):
        adapter.predict("not-eligible", None)  # type: ignore[arg-type]


def test_stub_adapter_refuses_even_with_eligible():
    """Guardrail: stub never fabricates a forecast, even on a valid Eligible."""
    adapter = StubAdapter()
    eligible = Eligible(
        model_id="kronos_base", horizon_bars=30, context_length=512, unverified=True
    )
    with pytest.raises(NotImplementedError):
        adapter.predict(eligible, None)


def test_eligible_models_for_filters():
    got = eligible_models_for(asset_class="stock", interval="1d", available_bars=10_000)
    ids = {m.id for m in got}
    assert "kronos_base" in ids
    # Mini needs 2200 bars; satisfied with 10k.
    assert "kronos_mini" in ids


def test_eligible_models_for_excludes_insufficient_history():
    got = eligible_models_for(asset_class="stock", interval="1d", available_bars=700)
    ids = {m.id for m in got}
    assert "kronos_mini" not in ids  # requires 2200


@pytest.mark.parametrize("model_id", ["kronos_base", "kronos_small", "kronos_mini"])
def test_every_registered_model_has_happy_path(model_id):
    result = EligibilityValidator.check(**_happy_path_args(model_id))
    assert isinstance(result, Eligible), f"{model_id}: {result}"
