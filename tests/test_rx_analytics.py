"""rx analytics — attribution-aware feedback metrics (retrieval-depth Phase 4).

Pure-function tests for ``app.rx.analytics``: the B4 (self-influence) and B3
(value-vs-engagement) de-biasing logic, no DB/model.
"""
from __future__ import annotations

from app.rx import analytics as an


# ---- action_rate -----------------------------------------------------------

def test_action_rate_excludes_dismissed_and_snoozed():
    # 2 acted, 2 skipped, 1 dismissed → 2/(2+2) = 0.5 (dismissed not in denom).
    disp = ["acted_as_prescribed", "acted_modified", "skipped", "skipped",
            "dismissed"]
    assert an.action_rate(disp) == 0.5


def test_action_rate_none_when_no_signal():
    assert an.action_rate(["dismissed", None]) is None
    assert an.action_rate([]) is None


def test_health_band_thresholds():
    assert an.health_band(0.30) == "green"
    assert an.health_band(0.29) == "yellow"
    assert an.health_band(0.15) == "yellow"
    assert an.health_band(0.14) == "red"
    assert an.health_band(None) == "unknown"


# ---- B4: creditable_trades / attribution -----------------------------------

def test_influenced_trades_excluded_from_lift():
    trades = [
        {"id": "1", "rec_influence_kind": "preceded_independent"},
        {"id": "2", "rec_influence_kind": "influenced"},   # caused → excluded
        {"id": "3", "rec_influence_kind": None},            # legacy → kept
    ]
    creditable = an.creditable_trades(trades)
    ids = {t["id"] for t in creditable}
    assert ids == {"1", "3"}  # the influenced trade cannot inflate lift


def test_attribution_summary_counts():
    trades = [
        {"rec_influence_kind": "preceded_independent"},
        {"rec_influence_kind": "influenced"},
        {"rec_influence_kind": "influenced"},
        {"rec_influence_kind": None},
    ]
    s = an.attribution_summary(trades)
    assert s == {"preceded_independent": 1, "influenced": 2, "unclassified": 1}


# ---- B3: P&L per rec / value-vs-engagement ---------------------------------

def test_pnl_per_rec_sums_closed_linked_trades():
    trades = [
        {"related_rec_id": "r1", "realized_pnl": 100.0},
        {"related_rec_id": "r1", "realized_pnl": -40.0},
        {"related_rec_id": "r2", "realized_pnl": 25.0},
        {"related_rec_id": None, "realized_pnl": 999.0},   # unlinked → ignored
        {"related_rec_id": "r3", "realized_pnl": None},     # open → ignored
    ]
    pnl = an.pnl_per_rec(trades)
    assert pnl == {"r1": 60.0, "r2": 25.0}


def test_value_vs_engagement_flags_divergence():
    # High engagement (all acted) but money-losing → the B3 trap.
    disp = ["acted_as_prescribed", "acted_as_prescribed", "acted_modified"]
    trades = [
        {"related_rec_id": "r1", "realized_pnl": -200.0},
        {"related_rec_id": "r2", "realized_pnl": 50.0},
    ]
    out = an.value_vs_engagement(disp, trades)
    assert out["action_rate"] == 1.0
    assert out["action_rate_band"] == "green"
    assert out["total_realized_pnl_on_recs"] == -150.0
    assert out["divergence_flag"] is True  # green engagement, red P&L


def test_value_vs_engagement_no_divergence_when_profitable():
    disp = ["acted_as_prescribed", "skipped"]
    trades = [{"related_rec_id": "r1", "realized_pnl": 300.0}]
    out = an.value_vs_engagement(disp, trades)
    assert out["divergence_flag"] is False


# ---- generic engagement_vs_value (non-finance doors) -----------------------

def test_generic_value_divergence_flags():
    # fitness: high adherence (engagement) but drift got WORSE (negative value)
    disp = ["acted_as_prescribed", "acted_modified", "acted_as_prescribed"]
    value = {"r1": -0.12, "r2": 0.03}  # net negative drift-improvement
    out = an.engagement_vs_value(disp, value, value_label="drift_improvement")
    assert out["action_rate_band"] == "green"
    assert out["total_value_on_recs"] == -0.09
    assert out["value_label"] == "drift_improvement"
    assert out["divergence_flag"] is True


def test_generic_value_no_divergence_when_positive():
    disp = ["acted_as_prescribed", "skipped"]
    value = {"r1": 0.20}
    out = an.engagement_vs_value(disp, value)
    assert out["divergence_flag"] is False
    assert out["value_label"] == "value"


def test_drift_improvement_per_rec():
    rows = [
        {"rec_id": "r1", "drift_before": 0.50, "drift_after": 0.30},  # +0.20 good
        {"rec_id": "r1", "drift_before": 0.30, "drift_after": 0.35},  # -0.05
        {"rec_id": "r2", "drift_before": 0.40, "drift_after": 0.40},  # 0
        {"rec_id": "r3", "drift_before": 0.5},                         # skip (no after)
    ]
    out = an.drift_improvement_per_rec(rows)
    assert abs(out["r1"] - 0.15) < 1e-9  # 0.20 + (-0.05)
    assert out["r2"] == 0.0
    assert "r3" not in out


def test_value_vs_engagement_backcompat_keys_present():
    # finance wrapper must still expose the original key names.
    out = an.value_vs_engagement(["acted_as_prescribed"],
                                 [{"related_rec_id": "r1", "realized_pnl": 10.0}])
    assert "total_realized_pnl_on_recs" in out
    assert "recs_with_pnl" in out
