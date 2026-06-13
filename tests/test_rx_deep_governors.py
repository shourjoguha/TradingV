"""Deep-result governors (retrieval-depth Phase 8).

Pure tests for the alarm-fatigue (NEW-1) + web-surface-bias (NEW-2) guards.
"""
from __future__ import annotations

from app.rx import deep_governors as g


# ---- contradiction severity (NEW-1: alarm fatigue) -------------------------

def test_pair_raises_high_banner():
    out = g.contradiction_severity({
        "contradictory_pairs": [{"a": "x", "b": "y", "conflict": "z"}],
        "contradicts_count": 0,
    })
    assert out["severity"] == "high"
    assert out["raise_banner"] is True


def test_two_contradictions_raise_high():
    out = g.contradiction_severity({"contradicts_count": 2})
    assert out["severity"] == "high"
    assert out["raise_banner"] is True


def test_single_contradiction_is_medium_banner():
    out = g.contradiction_severity({"contradicts_count": 1})
    assert out["severity"] == "medium"
    assert out["raise_banner"] is True


def test_only_staleness_no_banner():
    out = g.contradiction_severity({"contradicts_count": 0, "stale_count": 3})
    assert out["severity"] == "low"
    assert out["raise_banner"] is False  # alarm-fatigue guard: no banner on staleness alone


def test_aligned_no_banner():
    out = g.contradiction_severity({"contradicts_count": 0, "stale_count": 0})
    assert out["severity"] == "none"
    assert out["raise_banner"] is False


def test_contradicts_count_derived_from_sources():
    out = g.contradiction_severity({
        "sources": [
            {"stance": "contradicts"}, {"stance": "contradicts"},
            {"stance": "supports"},
        ],
    })
    assert out["contradicts_count"] == 2
    assert out["severity"] == "high"


# ---- disconfirmation credibility (NEW-2: web-surface bias) -----------------

def test_single_source_capped_at_thin_even_if_self_strong():
    out = g.disconfirmation_credibility({
        "strength": "strong",
        "sources": [{"publisher": "SomeBlog", "tier": "low"}],
    })
    assert out["credibility"] == "thin"   # single source can't be strong
    assert out["counts_against_thesis"] is False


def test_three_reputable_publishers_can_be_strong():
    out = g.disconfirmation_credibility({
        "strength": "strong",
        "sources": [
            {"publisher": "WSJ", "tier": "reputable"},
            {"publisher": "FT", "tier": "reputable"},
            {"publisher": "10-K", "tier": "primary"},
        ],
    })
    assert out["credibility"] == "strong"
    assert out["counts_against_thesis"] is True


def test_two_publishers_moderate():
    out = g.disconfirmation_credibility({
        "strength": "strong",
        "sources": [
            {"publisher": "WSJ", "tier": "reputable"},
            {"publisher": "Bloomberg", "tier": "reputable"},
        ],
    })
    assert out["credibility"] == "moderate"
    assert out["counts_against_thesis"] is True


def test_governor_never_inflates_above_self_report():
    # LLM honestly found nothing; many sources can't manufacture a counter.
    out = g.disconfirmation_credibility({
        "strength": "none",
        "sources": [
            {"publisher": "A", "tier": "reputable"},
            {"publisher": "B", "tier": "reputable"},
            {"publisher": "C", "tier": "primary"},
        ],
    })
    assert out["credibility"] == "none"
    assert out["counts_against_thesis"] is False


def test_no_sources_is_none():
    out = g.disconfirmation_credibility({"strength": "moderate", "sources": []})
    assert out["credibility"] == "none"


# ---- govern() dispatch -----------------------------------------------------

def test_govern_annotates_contradiction():
    out = g.govern("contradiction", {"contradicts_count": 2})
    assert out["governor"]["severity"] == "high"


def test_govern_annotates_disconfirmation():
    out = g.govern("disconfirmation",
                   {"strength": "strong", "sources": [{"publisher": "X", "tier": "low"}]})
    assert out["governor"]["credibility"] == "thin"


def test_govern_passes_through_other_kinds():
    p = {"candidates": [1, 2, 3]}
    assert g.govern("deep_retrieval", p) == p


def test_govern_handles_non_dict():
    assert g.govern("contradiction", None) is None
