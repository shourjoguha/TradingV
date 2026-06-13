"""rx analytics — attribution-aware feedback metrics (retrieval-depth Phase 4).

Pure functions (no DB, no I/O) so the de-biasing logic is fully unit-testable
and identical whether called from an endpoint or the /rx-analyze command.

Three limitations addressed:
  * B4 (self-influence flywheel): ``creditable_trades`` excludes trades the rec
    CAUSED (``rec_influence_kind == 'influenced'``) so predictive-lift only
    rewards recs that PRECEDED an independent decision.
  * B3 (complicity vs value): ``pnl_per_rec`` surfaces realized P&L per rec,
    a VALUE metric to sit beside the engagement metric ``action_rate``.
  * Honest action-rate: ``action_rate`` = acted / (acted + skipped); dismissed
    and snoozed are NOT in the denominator (matches /rx-analyze.md).
"""
from __future__ import annotations

from typing import Iterable, Optional

# Dispositions that count as "acted" in the numerator of action_rate.
_ACTED = {"acted_as_prescribed", "acted_modified"}


def action_rate(dispositions: Iterable[Optional[str]]) -> Optional[float]:
    """acted / (acted + skipped). dismissed + snoozed excluded.

    Returns None when the denominator is zero (no acted/skipped signal yet) —
    the caller decides how to surface "insufficient data" rather than this
    function inventing a 0.0 that reads like a real measurement.
    """
    acted = skipped = 0
    for d in dispositions:
        if d in _ACTED:
            acted += 1
        elif d == "skipped":
            skipped += 1
    denom = acted + skipped
    if denom == 0:
        return None
    return acted / denom


def health_band(rate: Optional[float]) -> str:
    """GREEN >=0.30 / YELLOW 0.15-0.30 / RED <0.15 / UNKNOWN when None."""
    if rate is None:
        return "unknown"
    if rate >= 0.30:
        return "green"
    if rate >= 0.15:
        return "yellow"
    return "red"


def creditable_trades(trades: Iterable[dict]) -> list[dict]:
    """Trades eligible for predictive-lift credit.

    Excludes trades the rec CAUSED (``rec_influence_kind == 'influenced'``).
    Keeps ``preceded_independent`` AND unclassified/legacy (NULL) — the
    operator classifies forward; we don't retroactively void legacy rows.
    This is the B4 break: an influenced trade can never inflate a rec's lift.
    """
    out = []
    for t in trades:
        if t.get("rec_influence_kind") == "influenced":
            continue
        out.append(t)
    return out


def attribution_summary(trades: Iterable[dict]) -> dict:
    """Counts by influence kind — for surfacing how much of the signal is
    self-influenced vs genuinely predictive."""
    counts = {"preceded_independent": 0, "influenced": 0, "unclassified": 0}
    for t in trades:
        kind = t.get("rec_influence_kind")
        if kind == "preceded_independent":
            counts["preceded_independent"] += 1
        elif kind == "influenced":
            counts["influenced"] += 1
        else:
            counts["unclassified"] += 1
    return counts


def pnl_per_rec(trades: Iterable[dict]) -> dict[str, float]:
    """Sum realized P&L per ``related_rec_id`` (B3 value metric).

    Only trades with a non-null ``related_rec_id`` and a non-null
    ``realized_pnl`` (i.e. closed) contribute. Returns ``{rec_id: pnl_sum}``.
    Attribution-neutral: includes influenced trades too, because realized P&L
    is a fact about money regardless of who caused the decision — it's the
    VALUE counterpart to the engagement metric, not the lift signal.
    """
    out: dict[str, float] = {}
    for t in trades:
        rec_id = t.get("related_rec_id")
        pnl = t.get("realized_pnl")
        if rec_id is None or pnl is None:
            continue
        out[rec_id] = out.get(rec_id, 0.0) + float(pnl)
    return out


def engagement_vs_value(
    dispositions: Iterable[Optional[str]],
    value_per_rec: dict[str, float],
    *,
    value_label: str = "value",
) -> dict:
    """Generic B3 divergence: engagement (action_rate) vs a pluggable VALUE
    signal per rec. The value signal is door-specific — realized P&L for
    finance, drift-composite improvement or goal-progress for the other doors
    — but the divergence logic is identical: a green action_rate with negative
    total value is the failure engagement-alone hides.

    ``value_per_rec`` maps rec_id → numeric value (sign convention: positive =
    good outcome). Returns a door-agnostic envelope; ``value_label`` names the
    unit for the caller's display.
    """
    rate = action_rate(dispositions)
    total_value = sum(value_per_rec.values())
    return {
        "action_rate": rate,
        "action_rate_band": health_band(rate),
        "value_label": value_label,
        "total_value_on_recs": total_value,
        "recs_with_value": len(value_per_rec),
        "divergence_flag": (
            rate is not None and rate >= 0.30 and total_value < 0
        ),
    }


def value_vs_engagement(
    dispositions: Iterable[Optional[str]],
    trades: Iterable[dict],
) -> dict:
    """Finance convenience wrapper (back-compat): value = realized P&L on
    rec-linked trades. Delegates to :func:`engagement_vs_value`. Adds
    finance-named aliases so existing callers/tests keep working.
    """
    pnl = pnl_per_rec(trades)
    out = engagement_vs_value(dispositions, pnl, value_label="realized_pnl")
    # Back-compat keys (the finance call site + tests expect these names).
    out["total_realized_pnl_on_recs"] = out["total_value_on_recs"]
    out["recs_with_pnl"] = out["recs_with_value"]
    return out


def drift_improvement_per_rec(rows: Iterable[dict]) -> dict[str, float]:
    """Non-finance value signal: drift-composite improvement attributable to a
    rec. ``rows`` carry ``rec_id``, ``drift_before``, ``drift_after`` (the
    door's drift composite at rec time vs after the rec's horizon). Value =
    ``drift_before - drift_after`` (positive = drift fell = the rec helped).
    Rows missing either score are skipped. This is the fitness/nutrition/
    learning analog of ``pnl_per_rec`` — value without money.
    """
    out: dict[str, float] = {}
    for r in rows:
        rec_id = r.get("rec_id")
        before = r.get("drift_before")
        after = r.get("drift_after")
        if rec_id is None or before is None or after is None:
            continue
        out[rec_id] = out.get(rec_id, 0.0) + (float(before) - float(after))
    return out
