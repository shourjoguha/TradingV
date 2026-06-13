"""Deep retrieval — filter-late classification (retrieval-depth Phase 1).

The graph-walk in ``deep_search`` needs the bge model + sqlite-vec and is
validated operator-side. The *filter-late* contract — nothing discarded,
every drop carries a reason, decay kept as a feature not a filter — lives in
the pure ``classify_candidates`` function, tested here without model or DB.

Gate evidence: proves the core operator requirement ("data not filtered out
before being evaluated") holds at the unit level.
"""
from __future__ import annotations

from tools.vault_indexer.graph_search import classify_candidates, DEEP_DEFAULTS


def test_deep_defaults_are_wider_than_fast():
    # Fast path: beam 5, prune 0.50, target 10. Deep must exceed all.
    assert DEEP_DEFAULTS["beam_width"] >= 12
    assert DEEP_DEFAULTS["prune_threshold"] <= 0.30
    assert DEEP_DEFAULTS["target_k"] >= 50
    assert DEEP_DEFAULTS["max_hops"] >= 4


def test_nothing_is_discarded():
    retained = [
        {"path": "a", "score": 0.8, "decay_weight": 1.0, "hop": 0},
        {"path": "b", "score": 0.5, "decay_weight": 0.6, "hop": 1},
    ]
    pruned = [
        {"path": "c", "similarity": 0.28, "hop": 1},
        {"path": "d", "similarity": 0.10, "hop": 2},
    ]
    out = classify_candidates(retained, pruned)
    # Every input survives — surfaced + dropped == all inputs.
    assert len(out["surfaced"]) == 2
    assert len(out["dropped"]) == 2


def test_every_drop_has_a_reason():
    pruned = [
        {"path": "c", "similarity": 0.28, "hop": 1},  # no reason yet
        {"path": "e", "similarity": 0.2, "hop": 2, "drop_reason": "beam_overflow"},
    ]
    out = classify_candidates([], pruned)
    reasons = {d["path"]: d["drop_reason"] for d in out["dropped"]}
    assert reasons["c"] == "below_prune_threshold"  # default applied
    assert reasons["e"] == "beam_overflow"          # explicit preserved


def test_decay_zero_is_kept_not_dropped():
    """A4 fix: an old filing (decay 0) must reach the judgment layer."""
    retained = [
        {"path": "old-10k", "score": 0.7, "decay_weight": 0.0, "hop": 2},
        {"path": "fresh", "score": 0.9, "decay_weight": 1.0, "hop": 0},
    ]
    out = classify_candidates(retained, [])
    surfaced_paths = [r["path"] for r in out["surfaced"]]
    assert "old-10k" in surfaced_paths  # kept despite decay 0
    old = next(r for r in out["surfaced"] if r["path"] == "old-10k")
    assert old["decay_zero"] is True
    assert old["retain_reason"] == "kept_despite_decay_zero"


def test_retain_reasons_assigned():
    retained = [
        {"path": "seed", "score": 0.9, "decay_weight": 1.0, "hop": 0},
        {"path": "hop1", "score": 0.6, "decay_weight": 0.8, "hop": 1},
    ]
    out = classify_candidates(retained, [])
    by_path = {r["path"]: r["retain_reason"] for r in out["surfaced"]}
    assert by_path["seed"] == "seed"
    assert by_path["hop1"] == "above_prune_floor"


def test_surfaced_sorted_by_score_desc():
    retained = [
        {"path": "lo", "score": 0.3, "decay_weight": 1.0, "hop": 1},
        {"path": "hi", "score": 0.9, "decay_weight": 1.0, "hop": 0},
        {"path": "mid", "score": 0.6, "decay_weight": 1.0, "hop": 1},
    ]
    out = classify_candidates(retained, [])
    assert [r["path"] for r in out["surfaced"]] == ["hi", "mid", "lo"]
