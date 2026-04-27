"""Hardcoded signal rules — Phase 3.1.

NOT a DSL by design. Three or four hardcoded rules cover the common cases.
Rules consume:
- ``predicted_close``, ``baseline_close`` from a PredictionPoint + its T0 actual
- ``horizon_offset`` (days into the future)
- ``hit_rate`` from accuracy_grid for the (ticker, horizon, model) pair
- ``min_samples`` (skip if accuracy data too thin to trust)

Each rule returns ``RuleHit | None``. The generator runs all rules over each
prediction; any non-None hits become Opportunity rows.

When the user wants tunable rules, replace this with a small DSL — but only
after we've seen which thresholds actually surface tradeable signals.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Optional


@dataclasses.dataclass(frozen=True)
class RuleHit:
    rule_id: str
    rule_label: str
    kind: str  # 'buy' | 'sell'
    predicted_move_pct: float  # signed; the actual predicted move
    confidence: float  # 0..1; usually historical hit-rate


@dataclasses.dataclass(frozen=True)
class RuleInput:
    ticker: str
    horizon_offset: int
    predicted_close: float
    baseline_close: float
    hit_rate: Optional[float]  # historical for (ticker, horizon, model)
    sample_count: int


def _move_pct(pred: float, base: float) -> float:
    if base <= 0:
        return 0.0
    return (pred - base) / base


def _r1_buy_5d(inp: RuleInput) -> Optional[RuleHit]:
    """+2% over 5d AND historical hit-rate ≥ 0.60 with ≥ 10 samples."""
    if inp.horizon_offset != 5:
        return None
    move = _move_pct(inp.predicted_close, inp.baseline_close)
    if move < 0.02:
        return None
    if inp.hit_rate is None or inp.hit_rate < 0.60 or inp.sample_count < 10:
        return None
    return RuleHit(
        rule_id="R1",
        rule_label="BUY +2% over 5d (HR≥60%)",
        kind="buy",
        predicted_move_pct=move,
        confidence=inp.hit_rate,
    )


def _r2_sell_5d(inp: RuleInput) -> Optional[RuleHit]:
    """-2% over 5d AND historical hit-rate ≥ 0.60 with ≥ 10 samples."""
    if inp.horizon_offset != 5:
        return None
    move = _move_pct(inp.predicted_close, inp.baseline_close)
    if move > -0.02:
        return None
    if inp.hit_rate is None or inp.hit_rate < 0.60 or inp.sample_count < 10:
        return None
    return RuleHit(
        rule_id="R2",
        rule_label="SELL -2% over 5d (HR≥60%)",
        kind="sell",
        predicted_move_pct=move,
        confidence=inp.hit_rate,
    )


def _r3_buy_10d(inp: RuleInput) -> Optional[RuleHit]:
    """+5% over 10d AND historical hit-rate ≥ 0.55 with ≥ 10 samples."""
    if inp.horizon_offset != 10:
        return None
    move = _move_pct(inp.predicted_close, inp.baseline_close)
    if move < 0.05:
        return None
    if inp.hit_rate is None or inp.hit_rate < 0.55 or inp.sample_count < 10:
        return None
    return RuleHit(
        rule_id="R3",
        rule_label="BUY +5% over 10d (HR≥55%)",
        kind="buy",
        predicted_move_pct=move,
        confidence=inp.hit_rate,
    )


RULES: list[Callable[[RuleInput], Optional[RuleHit]]] = [
    _r1_buy_5d,
    _r2_sell_5d,
    _r3_buy_10d,
]


def evaluate(inp: RuleInput) -> list[RuleHit]:
    """Run all rules; return the non-None hits."""
    hits: list[RuleHit] = []
    for rule in RULES:
        hit = rule(inp)
        if hit is not None:
            hits.append(hit)
    return hits
