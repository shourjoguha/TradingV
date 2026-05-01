"""Invalidator DSL — 5 ops, single ``evaluate`` entrypoint.

Shape: ``{"op": "<name>", "args": {...}}``. Validators reject unknown ops
or malformed arg shapes at create/update time so we never reach
:func:`evaluate` with bad input.

Ops:
- ``ratio_below_sma`` — ratio = M-1 ``compute_ratio(num, denom)``; fires
  when ratio < SMA(``sma_days``) for ``days_below`` consecutive trading
  days.
- ``series_above_threshold`` — raw ``MacroSeries`` symbol > threshold for
  ``days_above`` consecutive days.
- ``series_below_threshold`` — mirror of above; ``<`` strict.
- ``series_change_pct`` — % change of symbol over ``window_months`` exceeds
  ``threshold_pct`` in ``direction`` (``up`` or ``down``).
- ``manual`` — never auto-fires. Operator-only via cancel route.

Returns :class:`InvalidatorResult` with ``fired``, ``observed``, ``reason``.
``observed`` is the raw values inspected (kept for forensics on the
``hypothesis_evaluation.invalidator_result`` column).
"""
from __future__ import annotations

import datetime
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.macro.models import MacroSeries
from app.macro.service import compute_ratio


VALID_OPS = (
    "ratio_below_sma",
    "series_above_threshold",
    "series_below_threshold",
    "series_change_pct",
    "manual",
)

VALID_DIRECTIONS = ("up", "down")


@dataclass
class InvalidatorResult:
    fired: bool
    observed: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Validation (used by Pydantic schema layer)
# ----------------------------------------------------------------------

def validate_spec(spec: Any) -> None:
    """Raise ``ValueError`` if ``spec`` doesn't conform to the DSL."""
    if not isinstance(spec, dict):
        raise ValueError("invalidator must be an object")
    op = spec.get("op")
    if op not in VALID_OPS:
        raise ValueError(f"unknown invalidator op: {op!r}")
    args = spec.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("invalidator.args must be an object")

    if op == "ratio_below_sma":
        _require_str(args, "numerator")
        _require_str(args, "denominator")
        _require_pos_int(args, "sma_days")
        _require_pos_int(args, "days_below")
    elif op == "series_above_threshold":
        _require_str(args, "symbol")
        _require_number(args, "threshold")
        _require_pos_int(args, "days_above")
    elif op == "series_below_threshold":
        _require_str(args, "symbol")
        _require_number(args, "threshold")
        _require_pos_int(args, "days_below")
    elif op == "series_change_pct":
        _require_str(args, "symbol")
        _require_pos_int(args, "window_months")
        _require_number(args, "threshold_pct")
        d = args.get("direction")
        if d not in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {VALID_DIRECTIONS}")
    elif op == "manual":
        # No args required.
        pass


def _require_str(args: dict, key: str) -> None:
    v = args.get(key)
    if not isinstance(v, str) or not v:
        raise ValueError(f"args.{key} must be a non-empty string")


def _require_number(args: dict, key: str) -> None:
    v = args.get(key)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ValueError(f"args.{key} must be a number")


def _require_pos_int(args: dict, key: str) -> None:
    v = args.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise ValueError(f"args.{key} must be a positive integer")


# ----------------------------------------------------------------------
# Evaluation
# ----------------------------------------------------------------------

async def evaluate(spec: dict, *, session: AsyncSession) -> InvalidatorResult:
    """Evaluate a validated DSL spec against current macro data.

    Validation is the caller's responsibility (Pydantic does it at the
    route layer). This function trusts the shape.
    """
    op = spec["op"]
    args = spec.get("args", {})
    if op == "ratio_below_sma":
        return await _eval_ratio_below_sma(session, args)
    if op == "series_above_threshold":
        return await _eval_series_threshold(session, args, op="above")
    if op == "series_below_threshold":
        return await _eval_series_threshold(session, args, op="below")
    if op == "series_change_pct":
        return await _eval_series_change_pct(session, args)
    if op == "manual":
        return InvalidatorResult(
            fired=False,
            observed={},
            reason="manual op — never auto-fires",
        )
    raise ValueError(f"unknown op at evaluate(): {op!r}")


async def _eval_ratio_below_sma(
    session: AsyncSession, args: dict
) -> InvalidatorResult:
    sma_days = int(args["sma_days"])
    days_below = int(args["days_below"])
    # Pull enough history to compute SMA + a streak.
    since = datetime.date.today() - datetime.timedelta(
        days=sma_days + days_below + 30
    )
    points = await compute_ratio(
        numerator=args["numerator"],
        denominator=args["denominator"],
        since=since,
    )
    if len(points) < sma_days + days_below:
        return InvalidatorResult(
            fired=False,
            observed={"points": len(points), "needed": sma_days + days_below},
            reason="insufficient history",
        )
    values = [p["value"] for p in points]
    # SMA over the last window ending at each day; then check the trailing
    # ``days_below`` days are all strictly below their corresponding SMA.
    streak = 0
    for i in range(len(values) - days_below, len(values)):
        window_start = i - sma_days + 1
        if window_start < 0:
            break
        sma = statistics.fmean(values[window_start : i + 1])
        if values[i] < sma:
            streak += 1
        else:
            streak = 0
    fired = streak >= days_below
    last = values[-1] if values else None
    sma_last = (
        statistics.fmean(values[-sma_days:]) if len(values) >= sma_days else None
    )
    return InvalidatorResult(
        fired=fired,
        observed={
            "last_value": last,
            "last_sma": sma_last,
            "streak_days_below": streak,
            "required_streak": days_below,
        },
        reason=(
            f"ratio below {sma_days}-d SMA for {streak}/{days_below} days"
        ),
    )


async def _eval_series_threshold(
    session: AsyncSession, args: dict, *, op: str
) -> InvalidatorResult:
    """Generic threshold-streak op for raw MacroSeries values."""
    symbol = args["symbol"]
    threshold = float(args["threshold"])
    if op == "above":
        days_key = "days_above"
        comparator = lambda v: v > threshold  # noqa: E731
        verb = "above"
    else:
        days_key = "days_below"
        comparator = lambda v: v < threshold  # noqa: E731
        verb = "below"
    days_required = int(args[days_key])
    since = datetime.date.today() - datetime.timedelta(days=days_required + 14)
    rows = (
        await session.execute(
            select(MacroSeries.ts, MacroSeries.value)
            .where(MacroSeries.symbol == symbol)
            .where(MacroSeries.ts >= since)
            .order_by(MacroSeries.ts.asc())
        )
    ).all()
    values = [float(v) for _, v in rows]
    streak = 0
    for v in values[-days_required:]:
        if comparator(v):
            streak += 1
        else:
            streak = 0
    fired = streak >= days_required and len(values) >= days_required
    return InvalidatorResult(
        fired=fired,
        observed={
            "last_value": values[-1] if values else None,
            "threshold": threshold,
            "streak": streak,
            "required": days_required,
        },
        reason=f"{symbol} {verb} {threshold} for {streak}/{days_required} days",
    )


async def _eval_series_change_pct(
    session: AsyncSession, args: dict
) -> InvalidatorResult:
    symbol = args["symbol"]
    window_months = int(args["window_months"])
    threshold_pct = float(args["threshold_pct"])
    direction = args["direction"]
    # Approximate "N months" as 30 * N days for series lookups.
    since = datetime.date.today() - datetime.timedelta(
        days=window_months * 30 + 14
    )
    rows = (
        await session.execute(
            select(MacroSeries.ts, MacroSeries.value)
            .where(MacroSeries.symbol == symbol)
            .where(MacroSeries.ts >= since)
            .order_by(MacroSeries.ts.asc())
        )
    ).all()
    if len(rows) < 2:
        return InvalidatorResult(
            fired=False,
            observed={"points": len(rows)},
            reason="insufficient history",
        )
    base = float(rows[0][1])
    last = float(rows[-1][1])
    if base == 0:
        return InvalidatorResult(
            fired=False,
            observed={"base": base, "last": last},
            reason="base value zero — undefined % change",
        )
    pct = (last - base) / base * 100.0
    if direction == "up":
        fired = pct >= threshold_pct
    else:
        fired = pct <= -abs(threshold_pct)
    return InvalidatorResult(
        fired=fired,
        observed={"base": base, "last": last, "pct_change": pct},
        reason=f"{symbol} {direction} {pct:.2f}% over {window_months}mo",
    )
