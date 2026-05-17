"""Tests for ``vault_indexer.decay`` — Phase E Commit 2 ranked-grouped model.

Covers:
  - Evergreen flag short-circuits to 1.0
  - mode='off' yields 1.0 regardless of rank
  - mode='ranked_grouped' applies the ladder + floor
  - assign_ranks groups by group_key and orders by published_at desc
  - Edge cases: None published_at, missing path, single-member group

Module reloads are used to flip env between tests because the decay module
reads CONFIG at call time (not via injection), so DECAY_MODE / DECAY_LADDER
have to be set before `from vault_indexer import decay`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


_DECAY_ENV_KEYS = (
    "DOMAIN", "DECAY_MODE", "DECAY_LADDER", "DECAY_FLOOR",
    "DECAY_GROUP_KEY", "DECAY_EVERGREEN_PATHS",
    "INCLUDE_FOLDERS", "EXCLUDE_FOLDERS",
)


def _reload(env: dict, tmp_path):
    """Reset vault_indexer modules with the given env. Returns the decay module.

    Clears all decay-related env vars first so tests don't inherit prior state.
    """
    import os
    # Clear stale decay env from previous tests
    for k in _DECAY_ENV_KEYS:
        os.environ.pop(k, None)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    os.environ["VAULT_PATH"] = str(tmp_path)
    os.environ.setdefault("AUTO_TAG_ENABLED", "0")
    for m in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[m]
    from vault_indexer import decay
    return decay


# ---------------------------------------------------------------------------
# weight_for
# ---------------------------------------------------------------------------

def test_evergreen_node_always_weighted_one(tmp_path):
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    node = {"evergreen": True, "author": "graham"}
    # Evergreen wins over any rank.
    assert decay.weight_for(node) == 1.0
    assert decay.weight_for(node, rank=0) == 1.0
    assert decay.weight_for(node, rank=99) == 1.0


def test_off_mode_returns_one_for_all_ranks(tmp_path):
    decay = _reload({"DECAY_MODE": "off"}, tmp_path)
    node = {"author": "damodaran", "evergreen": False}
    for r in (0, 1, 5, 100):
        assert decay.weight_for(node, rank=r) == 1.0


def test_ranked_grouped_ladder_application(tmp_path):
    decay = _reload(
        {"DECAY_MODE": "ranked_grouped", "DECAY_LADDER": "1.0,0.6,0.45,0.35,0.25"},
        tmp_path,
    )
    node = {"author": "damodaran", "evergreen": False}
    assert decay.weight_for(node, rank=0) == 1.0
    assert decay.weight_for(node, rank=1) == 0.6
    assert decay.weight_for(node, rank=2) == 0.45
    assert decay.weight_for(node, rank=3) == 0.35
    assert decay.weight_for(node, rank=4) == 0.25
    # Past ladder → floor (last rung by default).
    assert decay.weight_for(node, rank=5) == 0.25
    assert decay.weight_for(node, rank=20) == 0.25


def test_custom_floor_via_env(tmp_path):
    decay = _reload(
        {
            "DECAY_MODE": "ranked_grouped",
            "DECAY_LADDER": "1.0,0.5",
            "DECAY_FLOOR": "0.1",
        },
        tmp_path,
    )
    node = {"author": "x", "evergreen": False}
    assert decay.weight_for(node, rank=0) == 1.0
    assert decay.weight_for(node, rank=1) == 0.5
    assert decay.weight_for(node, rank=2) == 0.1  # past ladder → floor


def test_ungrouped_node_no_penalty(tmp_path):
    """rank=None (caller didn't assign) → 1.0. Preserves legacy behaviour
    for unauthored content (Notes/, Topics/)."""
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    node = {"author": None, "evergreen": False}
    assert decay.weight_for(node, rank=None) == 1.0


# ---------------------------------------------------------------------------
# assign_ranks
# ---------------------------------------------------------------------------

def test_assign_ranks_orders_within_group(tmp_path):
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    nodes = [
        {"path": "old.md", "author": "a", "published_at": "2026-01-01"},
        {"path": "new.md", "author": "a", "published_at": "2026-05-15"},
        {"path": "mid.md", "author": "a", "published_at": "2026-03-10"},
    ]
    r = decay.assign_ranks(nodes, group_key="author")
    assert r["new.md"] == 0
    assert r["mid.md"] == 1
    assert r["old.md"] == 2


def test_assign_ranks_separate_groups_per_author(tmp_path):
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    nodes = [
        {"path": "a1.md", "author": "alpha", "published_at": "2026-05-10"},
        {"path": "b1.md", "author": "beta",  "published_at": "2026-05-01"},
        {"path": "a2.md", "author": "alpha", "published_at": "2026-04-01"},
    ]
    r = decay.assign_ranks(nodes, group_key="author")
    # Each author group ranks independently.
    assert r["a1.md"] == 0
    assert r["a2.md"] == 1
    assert r["b1.md"] == 0  # solo in beta group


def test_assign_ranks_missing_author_skipped(tmp_path):
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    nodes = [
        {"path": "x.md", "author": None, "published_at": "2026-05-10"},
        {"path": "y.md", "author": "",   "published_at": "2026-05-10"},
        {"path": "z.md", "author": "ok", "published_at": "2026-05-10"},
    ]
    r = decay.assign_ranks(nodes, group_key="author")
    assert "x.md" not in r
    assert "y.md" not in r
    assert r["z.md"] == 0


def test_assign_ranks_none_published_at_floats_to_end(tmp_path):
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    nodes = [
        {"path": "dated.md",  "author": "a", "published_at": "2026-05-10"},
        {"path": "no-date.md", "author": "a", "published_at": None},
    ]
    r = decay.assign_ranks(nodes, group_key="author")
    assert r["dated.md"] == 0
    assert r["no-date.md"] == 1


def test_assign_ranks_missing_path_skipped(tmp_path):
    """Nodes without a 'path' key are ignored (defensive)."""
    decay = _reload({"DECAY_MODE": "ranked_grouped"}, tmp_path)
    nodes = [{"author": "a", "published_at": "2026-05-10"}]
    r = decay.assign_ranks(nodes, group_key="author")
    assert r == {}


# ---------------------------------------------------------------------------
# Config: is_evergreen_path
# ---------------------------------------------------------------------------

def test_is_evergreen_path_books_match(tmp_path):
    """finance config (Books/** evergreen)."""
    _ = _reload({"DECAY_EVERGREEN_PATHS": "Books/**"}, tmp_path)
    from vault_indexer.config import CONFIG
    assert CONFIG.is_evergreen_path("Books/graham/intro.md") is True
    assert CONFIG.is_evergreen_path("Videos/click-capital/2026-w19.md") is False
    assert CONFIG.is_evergreen_path("Filings/AAPL/q1.md") is False


def test_is_evergreen_path_wildcard_match(tmp_path):
    """fitness/nutrition config (**) — all paths evergreen."""
    _ = _reload({"DECAY_EVERGREEN_PATHS": "**"}, tmp_path)
    from vault_indexer.config import CONFIG
    assert CONFIG.is_evergreen_path("Videos/fitness/galpin/intro.md") is True
    assert CONFIG.is_evergreen_path("Books/fitness/attia/ch1.md") is True


def test_is_evergreen_path_no_globs_returns_none(tmp_path):
    """No globs configured → None (caller treats as unclassified)."""
    _ = _reload({"DECAY_EVERGREEN_PATHS": ""}, tmp_path)
    from vault_indexer.config import CONFIG
    # Explicit empty CSV → tuple() → returns None.
    assert CONFIG.is_evergreen_path("Books/anything.md") is None


# ---------------------------------------------------------------------------
# Per-kind overrides (Filings: group by ticker, keep last 2)
# ---------------------------------------------------------------------------

def _seed_kind_override_registry(tmp_path):
    """Write a minimal _domains.yaml with filings kind_overrides."""
    (tmp_path / "_domains.yaml").write_text(
        "domains:\n"
        "  test:\n"
        "    legacy: true\n"
        "    decay:\n"
        "      mode: ranked_grouped\n"
        "      group_key: author\n"
        "      ladder: [1.0, 0.6, 0.45, 0.35, 0.25]\n"
        "      floor: 0.25\n"
        "      evergreen_paths: ['Books/**']\n"
        "      kind_overrides:\n"
        "        filing:\n"
        "          group_by_path_prefix: 'Filings/'\n"
        "          ladder: [1.0, 0.6]\n"
        "          floor: 0.0\n",
        encoding="utf-8",
    )


def test_filings_group_by_ticker(tmp_path):
    """Filings/AAPL/* group by AAPL; Filings/MSFT/* group by MSFT."""
    _seed_kind_override_registry(tmp_path)
    decay = _reload({"DOMAIN": "test"}, tmp_path)
    nodes = [
        {"path": "Filings/AAPL/2026-q1.md", "kind": "filing", "author": None,
         "published_at": "2026-05-01"},
        {"path": "Filings/AAPL/2025-q4.md", "kind": "filing", "author": None,
         "published_at": "2026-02-01"},
        {"path": "Filings/AAPL/2025-q3.md", "kind": "filing", "author": None,
         "published_at": "2025-11-01"},
        {"path": "Filings/MSFT/2026-q1.md", "kind": "filing", "author": None,
         "published_at": "2026-04-15"},
    ]
    from vault_indexer.config import CONFIG
    ranks = decay.assign_ranks(
        nodes, group_key="author", kind_overrides=CONFIG.decay_kind_overrides,
    )
    # AAPL group: most recent = rank 0
    assert ranks["Filings/AAPL/2026-q1.md"] == 0
    assert ranks["Filings/AAPL/2025-q4.md"] == 1
    assert ranks["Filings/AAPL/2025-q3.md"] == 2
    # MSFT solo group
    assert ranks["Filings/MSFT/2026-q1.md"] == 0


def test_filings_weight_drops_past_rank_1(tmp_path):
    """Filings rank ≥ 2 → weight = 0 (the floor), which search drops."""
    _seed_kind_override_registry(tmp_path)
    decay = _reload({"DOMAIN": "test"}, tmp_path)
    node = {"kind": "filing", "evergreen": False}
    assert decay.weight_for(node, rank=0) == 1.0
    assert decay.weight_for(node, rank=1) == 0.6
    assert decay.weight_for(node, rank=2) == 0.0
    assert decay.weight_for(node, rank=10) == 0.0


def test_non_filing_uses_default_ladder(tmp_path):
    """Override only applies to matching kind; videos still use default ladder."""
    _seed_kind_override_registry(tmp_path)
    decay = _reload({"DOMAIN": "test"}, tmp_path)
    video = {"kind": "video", "evergreen": False, "author": "click-capital"}
    assert decay.weight_for(video, rank=0) == 1.0
    assert decay.weight_for(video, rank=1) == 0.6
    assert decay.weight_for(video, rank=2) == 0.45  # default ladder, not 0
    assert decay.weight_for(video, rank=10) == 0.25  # default floor


def test_filing_with_author_uses_author_grouping(tmp_path):
    """If a filing happens to carry author frontmatter, the override path
    grouping wins (kind dominates the override decision). Documented behaviour
    so operator can rely on the override being kind-driven."""
    _seed_kind_override_registry(tmp_path)
    decay = _reload({"DOMAIN": "test"}, tmp_path)
    nodes = [
        {"path": "Filings/AAPL/2026-q1.md", "kind": "filing",
         "author": "weirdly-set", "published_at": "2026-05-01"},
        {"path": "Filings/AAPL/2025-q4.md", "kind": "filing",
         "author": "weirdly-set", "published_at": "2026-02-01"},
    ]
    from vault_indexer.config import CONFIG
    ranks = decay.assign_ranks(
        nodes, group_key="author", kind_overrides=CONFIG.decay_kind_overrides,
    )
    # Both should group by AAPL via path prefix, NOT by author "weirdly-set"
    # → separate ranks within the AAPL group.
    assert ranks["Filings/AAPL/2026-q1.md"] == 0
    assert ranks["Filings/AAPL/2025-q4.md"] == 1


def test_filing_without_matching_prefix_falls_back_to_author(tmp_path):
    """If path doesn't match Filings/, override prefix doesn't apply →
    fall back to author grouping (or skip if no author)."""
    _seed_kind_override_registry(tmp_path)
    decay = _reload({"DOMAIN": "test"}, tmp_path)
    nodes = [
        {"path": "Research/aapl-thesis.md", "kind": "filing",
         "author": "operator", "published_at": "2026-05-01"},
    ]
    from vault_indexer.config import CONFIG
    ranks = decay.assign_ranks(
        nodes, group_key="author", kind_overrides=CONFIG.decay_kind_overrides,
    )
    # Falls back to author=operator grouping → solo group, rank 0
    assert ranks["Research/aapl-thesis.md"] == 0
