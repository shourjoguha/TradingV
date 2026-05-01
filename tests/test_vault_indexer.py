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


def test_decay_weight_class_a_is_one(tmp_vault):
    from vault_indexer import decay

    node = {"horizon_months": None, "published_at": "2024-01-01"}
    assert decay.weight_for(node) == 1.0


def test_decay_weight_class_b_decreases_with_age():
    from vault_indexer import decay

    fresh = {"horizon_months": 6, "published_at": "2026-05-01"}
    aged = {"horizon_months": 6, "published_at": "2025-05-01"}
    fresh_w = decay.weight_for(fresh)
    aged_w = decay.weight_for(aged)
    assert 0 < aged_w < fresh_w <= 1.0


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
