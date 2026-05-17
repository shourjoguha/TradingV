"""Tests for the vault-indexer sidecar — Phase 2.

Smoke + unit coverage. Skips silently if the sentence-transformers model
isn't reachable so the rest of the TradingView suite isn't blocked on
embedding loads.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# tools/ is not a package by default; stitch path so we can import.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# Force a temp vault per test BEFORE the indexer modules read CONFIG.
# We must wipe the package out of sys.modules so submodule imports re-bind
# their `from .config import CONFIG` references to the env we just set.
@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("INDEXER_DB_PATH", str(tmp_path / ".indexer" / "cache.db"))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")  # never call Anthropic in tests
    for mod in [m for m in list(sys.modules) if m == "vault_indexer" or m.startswith("vault_indexer.")]:
        del sys.modules[mod]
    return tmp_path


def _embedding_available() -> bool:
    """Lightweight probe — checks the local HF cache without loading the model."""
    home = Path.home() / ".cache" / "huggingface" / "hub"
    return (home / "models--BAAI--bge-large-en-v1.5").exists()


def test_taxonomy_parser_basic():
    from vault_indexer import taxonomy

    text = """# Taxonomy

## Active tags

- `liquidity` — central bank balance sheet
- `btc` — bitcoin notes

## RENAMES (one-shot; remove lines after indexer applies)

<!-- format: old_name → new_name -->
old_thing → new_thing
"""
    tx = taxonomy.parse(text)
    assert "liquidity" in tx.tags
    assert tx.tags["btc"].startswith("bitcoin")
    assert tx.renames == [("old_thing", "new_thing")]


def test_taxonomy_strip_renames_idempotent():
    from vault_indexer import taxonomy

    text = (
        "## RENAMES (one-shot; remove lines after indexer applies)\n"
        "old → new\n"
        "kept → unchanged\n"
    )
    stripped = taxonomy.strip_renames(text, [("old", "new")])
    assert "old → new" not in stripped
    assert "kept → unchanged" in stripped
    # Idempotent re-strip.
    again = taxonomy.strip_renames(stripped, [("old", "new")])
    assert again == stripped


def test_renames_rewrite_frontmatter(tmp_vault):
    from vault_indexer import renames

    note = tmp_vault / "Notes" / "thoughts.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\nkind: note\ntags: [old_thing, btc]\n---\n# Thoughts\n",
        encoding="utf-8",
    )
    tax = tmp_vault / "_taxonomy.md"
    tax.write_text(
        "## Active tags\n- `btc` — bitcoin\n## RENAMES (one-shot; remove lines after indexer applies)\nold_thing → new_thing\n",
        encoding="utf-8",
    )
    log = renames.apply_renames(tmp_vault, tax)
    assert log == [("old_thing", "new_thing", 1)]
    rewritten = note.read_text(encoding="utf-8")
    assert "new_thing" in rewritten
    assert "old_thing" not in rewritten
    # Rename directive removed from taxonomy.
    assert "old_thing → new_thing" not in tax.read_text(encoding="utf-8")


def test_decay_weight_ungrouped_is_one(tmp_vault):
    """Legacy "Class A" / ungrouped behaviour: no rank → no penalty.

    Pre-Phase-E.2 the model was exponential on ``horizon_months``. The new
    model decays only same-author groups; solo / ungrouped nodes get
    weight = 1.0 regardless of age. Use the rank-based test below for the
    decay-applied case.
    """
    from vault_indexer import decay

    node = {"horizon_months": None, "published_at": "2024-01-01"}
    assert decay.weight_for(node) == 1.0
    aged = {"horizon_months": 6, "published_at": "2025-05-01"}
    # No rank passed → ungrouped → 1.0 under new model.
    assert decay.weight_for(aged) == 1.0


def test_decay_weight_evergreen_bypasses_rank(tmp_vault):
    """Evergreen flag short-circuits to 1.0 even with a rank assigned."""
    from vault_indexer import decay

    node = {"evergreen": True, "author": "graham"}
    assert decay.weight_for(node, rank=4) == 1.0


def test_decay_ladder_applies_to_grouped_nodes(tmp_vault, monkeypatch):
    """ranked_grouped mode: ladder weights applied per rank, floor at end."""
    monkeypatch.setenv("DOMAIN", "finance")
    monkeypatch.setenv("DECAY_MODE", "ranked_grouped")
    monkeypatch.setenv("DECAY_LADDER", "1.0,0.6,0.45,0.35,0.25")
    import sys
    for m in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[m]
    from vault_indexer import decay

    node = {"author": "damodaran", "evergreen": False}
    assert decay.weight_for(node, rank=0) == 1.0
    assert decay.weight_for(node, rank=1) == 0.6
    assert decay.weight_for(node, rank=2) == 0.45
    assert decay.weight_for(node, rank=3) == 0.35
    assert decay.weight_for(node, rank=4) == 0.25
    # Rank past ladder collapses to floor.
    assert decay.weight_for(node, rank=10) == 0.25


def test_assign_ranks_orders_by_published_at_desc(tmp_vault):
    """assign_ranks groups by author and orders by published_at desc."""
    from vault_indexer import decay

    nodes = [
        {"path": "a.md", "author": "damodaran", "published_at": "2026-05-01"},
        {"path": "b.md", "author": "damodaran", "published_at": "2026-05-10"},
        {"path": "c.md", "author": "damodaran", "published_at": "2026-04-20"},
        {"path": "d.md", "author": "lyn-alden", "published_at": "2026-05-15"},
        {"path": "e.md", "author": None,        "published_at": "2026-05-15"},
    ]
    ranks = decay.assign_ranks(nodes, group_key="author")
    assert ranks["b.md"] == 0  # most recent damodaran
    assert ranks["a.md"] == 1
    assert ranks["c.md"] == 2
    assert ranks["d.md"] == 0  # solo in lyn-alden group
    assert "e.md" not in ranks  # no author → no group entry


def test_review_render_and_tick_parse():
    from vault_indexer import review

    suggestions = {
        "auto_tags": {"Notes/a.md": ["liquidity", "btc"]},
        "cross_links": {"Notes/a.md": [("Notes/b.md", 0.84)]},
        "orphan_tags": [("legacy_tag", 3)],
        "rename_log": [],
    }
    md = review.render(suggestions)
    assert "Auto-tag suggestions" in md
    assert "Notes/a.md" in md
    assert "[ ] tag: `liquidity`" in md
    # Now simulate the operator ticking the first tag.
    md_ticked = md.replace("[ ] tag: `liquidity`", "[x] tag: `liquidity`", 1)
    ticks = review.parse_ticks(md_ticked)
    assert ("tag", {"path": "Notes/a.md", "tag": "liquidity"}) in ticks


def test_vault_chunk_body_splits_on_headings():
    from vault_indexer.vault import chunk_body

    body = "# Intro\n\nthis is a short intro.\n\n# Long\n\n" + ("alpha " * 800)
    chunks = chunk_body(body, target_tokens=300, overlap_tokens=50)
    # Intro alone fits in one chunk; the long section gets split.
    assert any(c[1] == "Intro" for c in chunks)
    long_chunks = [c for c in chunks if c[1] == "Long"]
    assert len(long_chunks) >= 2


def test_review_promote_appends_tag(tmp_vault):
    from vault_indexer import review

    note = tmp_vault / "Notes" / "a.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\nkind: note\ntags: [btc]\n---\n# A\nbody\n", encoding="utf-8"
    )
    ticks = [("tag", {"path": "Notes/a.md", "tag": "liquidity"})]
    # promote() needs a connection; pass None — tag-path doesn't touch the DB.
    counts = review.promote(None, tmp_vault, ticks)
    assert counts["tags_added"] == 1
    rewritten = note.read_text(encoding="utf-8")
    assert "liquidity" in rewritten
    assert "btc" in rewritten  # original preserved


@pytest.mark.skipif(
    not _embedding_available(),
    reason="bge-large not in HF cache; skip end-to-end embed test",
)
def test_index_and_search_end_to_end(tmp_vault):
    """Full smoke — write a note, ingest, search, get it back."""
    from vault_indexer import cache, indexer, search
    from vault_indexer.vault import parse_file

    # One note about stagflation, one unrelated.
    a = tmp_vault / "Notes" / "stag.md"
    a.parent.mkdir(parents=True)
    a.write_text(
        "---\nkind: note\ntitle: Stagflation regime\ntags: [regime_shift]\n---\n"
        "# Stagflation\n\n"
        "Persistent inflation alongside stagnant growth. "
        "Real yields stay negative, gold tends to outperform equities.\n",
        encoding="utf-8",
    )
    b = tmp_vault / "Notes" / "kitchen.md"
    b.write_text(
        "---\nkind: note\ntitle: Sourdough\n---\n# Sourdough\n\n"
        "Mixing flour and water for a wild yeast starter; needs 7-10 days.\n",
        encoding="utf-8",
    )

    from vault_indexer.config import CONFIG
    con = cache.init(CONFIG.db_path, CONFIG.embedding_dim)
    indexer.full_rescan(con)

    results = search.search(con, "stagflation regime", k=2)
    assert results, "expected at least one result"
    assert results[0]["path"] == "Notes/stag.md"
    assert results[0]["similarity"] > results[-1]["similarity"]


def test_folder_context_index_md_skips_chunks_and_resolves_via_path_walk(tmp_vault):
    """`_index.md` files must:
       1. Be ingestable (kind coerced to folder_context regardless of frontmatter)
       2. NOT produce chunk rows (zero embedding cost; never appear in evidence)
       3. Be reachable from any descendant evidence path via `folder_contexts_for`
    Pure-path test — does not require a working embedder."""
    from vault_indexer import cache, indexer
    from vault_indexer.vault import scan

    channel_dir = tmp_vault / "Videos" / "fx-evolution-daily"
    channel_dir.mkdir(parents=True)
    (channel_dir / "_index.md").write_text(
        "---\nkind: anything-the-operator-typed\ntitle: FX Evolution channel\n---\n"
        "Daily FX setup. Default grain daily; weekly callouts explicit.\n",
        encoding="utf-8",
    )
    (channel_dir / "2026-05-06-dxy-pivot.md").write_text(
        "---\nkind: video\ntitle: DXY pivot\n---\n"
        "Body about DXY pivot setup and rate path.\n",
        encoding="utf-8",
    )
    # Also a top-level `Videos/_index.md` to confirm two-level chain.
    (tmp_vault / "Videos" / "_index.md").write_text(
        "---\ntitle: Videos collection\n---\n"
        "Convention: per-channel folders with `_index.md`.\n",
        encoding="utf-8",
    )

    from vault_indexer.config import CONFIG
    con = cache.init(CONFIG.db_path, CONFIG.embedding_dim)

    # `_index.md` must be ingestable now.
    nodes = list(scan(tmp_vault))
    paths_seen = {n.rel_path for n in nodes}
    assert "Videos/_index.md" in paths_seen
    assert "Videos/fx-evolution-daily/_index.md" in paths_seen
    # Auto-coerced kind regardless of any frontmatter the operator typed.
    by_path = {n.rel_path: n for n in nodes}
    assert by_path["Videos/fx-evolution-daily/_index.md"].kind == "folder_context"
    assert by_path["Videos/_index.md"].kind == "folder_context"

    # Index just the two _index.md files (not the video; embedder may not be loaded).
    indexer.index_one(con, by_path["Videos/_index.md"])
    indexer.index_one(con, by_path["Videos/fx-evolution-daily/_index.md"])

    # No chunks produced for folder_context kind.
    chunk_count = list(con.execute(
        "SELECT COUNT(*) FROM vault_chunk WHERE path = ?",
        ("Videos/fx-evolution-daily/_index.md",),
    ))[0][0]
    assert chunk_count == 0
    chunk_count_top = list(con.execute(
        "SELECT COUNT(*) FROM vault_chunk WHERE path = ?",
        ("Videos/_index.md",),
    ))[0][0]
    assert chunk_count_top == 0

    # folder_contexts_for walks ancestors and returns both vignettes
    # ordered root-first.
    out = cache.folder_contexts_for(
        con, ["Videos/fx-evolution-daily/2026-05-06-dxy-pivot.md"]
    )
    paths = [r["path"] for r in out]
    assert paths == [
        "Videos/_index.md",
        "Videos/fx-evolution-daily/_index.md",
    ]
    assert all(
        r["applies_to"] == ["Videos/fx-evolution-daily/2026-05-06-dxy-pivot.md"]
        for r in out
    )
    # Body is preserved verbatim — no truncation in the cache layer.
    fx_body = next(r for r in out if "fx-evolution-daily" in r["path"])["body"]
    assert "Default grain daily" in fx_body
