"""Drift monitors — preference drift + embedding shift (retrieval-depth Phase 6).

Pure-function tests on synthetic series. Gate evidence: the detectors fire on a
declining-action-rate trend and on an injected embedding-distribution shift, and
stay quiet on stable/insufficient inputs.
"""
from __future__ import annotations

import math

from app.rx import drift_monitor as dm


# ---- linear_slope ----------------------------------------------------------

def test_slope_none_for_short_series():
    assert dm.linear_slope([]) is None
    assert dm.linear_slope([0.5]) is None


def test_slope_sign_and_magnitude():
    # perfectly increasing by 0.1/step
    assert math.isclose(dm.linear_slope([0.0, 0.1, 0.2, 0.3]), 0.1, abs_tol=1e-9)
    # perfectly decreasing
    assert math.isclose(dm.linear_slope([0.4, 0.3, 0.2, 0.1]), -0.1, abs_tol=1e-9)
    # flat
    assert dm.linear_slope([0.3, 0.3, 0.3]) == 0.0


# ---- preference_drift ------------------------------------------------------

def test_declining_preference_flagged():
    # action_rate falling 0.5 → 0.2 over 4 weeks
    out = dm.preference_drift([0.5, 0.4, 0.3, 0.2], slope_threshold=0.05)
    assert out["drifting"] is True
    assert out["direction"] == "declining"
    assert out["slope"] < 0


def test_improving_preference_flagged():
    out = dm.preference_drift([0.2, 0.3, 0.45, 0.6], slope_threshold=0.05)
    assert out["drifting"] is True
    assert out["direction"] == "improving"


def test_stable_preference_not_flagged():
    out = dm.preference_drift([0.31, 0.30, 0.32, 0.30], slope_threshold=0.05)
    assert out["drifting"] is False
    assert out["direction"] == "stable"


def test_insufficient_data():
    out = dm.preference_drift([0.3])
    assert out["direction"] == "insufficient_data"
    assert out["drifting"] is False


def test_threshold_respected():
    # gentle decline below threshold → not flagged
    out = dm.preference_drift([0.50, 0.49, 0.48, 0.47], slope_threshold=0.05)
    assert out["drifting"] is False  # slope -0.01, under 0.05


# ---- embedding shift -------------------------------------------------------

def test_no_shift_for_identical_centroid():
    c = [1.0, 0.0, 0.0]
    out = dm.embedding_centroid_shift(c, c, distance_threshold=0.15)
    assert out["shifted"] is False
    assert math.isclose(out["distance"], 0.0, abs_tol=1e-9)


def test_shift_flagged_for_divergent_centroid():
    # orthogonal vectors → cosine 0 → distance 1.0 → way past threshold
    out = dm.embedding_centroid_shift([1.0, 0.0], [0.0, 1.0], distance_threshold=0.15)
    assert out["shifted"] is True
    assert math.isclose(out["distance"], 1.0, abs_tol=1e-9)


def test_small_shift_under_threshold():
    # nearly-parallel vectors → tiny distance → not flagged
    out = dm.embedding_centroid_shift([1.0, 0.0], [0.99, 0.01],
                                      distance_threshold=0.15)
    assert out["shifted"] is False


def test_centroid_mean():
    assert dm.centroid([[2.0, 0.0], [0.0, 4.0]]) == [1.0, 2.0]
    assert dm.centroid([]) is None
    assert dm.centroid([[1.0, 2.0], [1.0]]) is None  # ragged
