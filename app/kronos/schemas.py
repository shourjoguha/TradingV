"""Kronos eligibility result types.

An analysis request becomes either `Eligible` (carries a resolved model spec
and horizon) or `Ineligible` (carries a structured reason + human message).
Code downstream of the validator MUST pattern-match on this type — the
adapter refuses to run without an `Eligible` instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Union


class IneligibleReason(str, Enum):
    UNSUPPORTED_INTERVAL = "UNSUPPORTED_INTERVAL"
    UNSUPPORTED_ASSET = "UNSUPPORTED_ASSET"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_FEATURES = "MISSING_FEATURES"
    UNKNOWN_MODEL = "UNKNOWN_MODEL"
    HORIZON_OUT_OF_RANGE = "HORIZON_OUT_OF_RANGE"
    MODEL_CONSTRAINT = "MODEL_CONSTRAINT"


@dataclass(frozen=True)
class Eligible:
    kind: Literal["eligible"] = "eligible"
    model_id: str = ""
    horizon_bars: int = 0
    context_length: int = 0
    unverified: bool = True  # reflects spec.unverified — callers warn on true


@dataclass(frozen=True)
class Ineligible:
    reason: IneligibleReason
    message: str
    kind: Literal["ineligible"] = "ineligible"


EligibilityResult = Union[Eligible, Ineligible]
