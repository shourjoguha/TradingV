"""Tests for domain-isolation guarantees in the multi-domain vault setup.

Two tiers:

  1. Unit tests on ``passes_scope()`` with a synthetic ``_domains.yaml`` —
     fast, model-free, regression-detection for the registry parser.
  2. Integration test that ingests a mixed finance/fitness corpus into two
     separate caches and asserts no cross-pollination. Skipped silently
     when the BGE model isn't available locally (consistent with the rest
     of ``test_vault_indexer.py``).

The unit tests are the primary safety net. The integration test is the
"belt-and-suspenders" check — catches anything the unit tests miss because
the ingest pipeline composes ``passes_scope`` with other filters.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# tools/ is not a package by default; stitch path so we can import.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


SAMPLE_REGISTRY = """\
domains:
  finance:
    legacy: true
    taxonomy_file: _taxonomy.md
    review_file: _review-queue.md

  fitness:
    classes: [Books, Newsletters, Videos, Topics]
    taxonomy_file: _taxonomy-fitness.md
    review_file: _review-queue-fitness.md

  nutrition:
    classes: [Books, Newsletters, Videos, Topics]
    taxonomy_file: _taxonomy-nutrition.md
    review_file: _review-queue-nutrition.md
"""


@pytest.fixture
def tmp_vault_with_registry(tmp_path, monkeypatch):
    """Tmp vault containing a 3-domain ``_domains.yaml``. Wipes
    ``vault_indexer`` from ``sys.modules`` so the next import re-reads env.
    """
    (tmp_path / "_domains.yaml").write_text(SAMPLE_REGISTRY, encoding="utf-8")
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    for mod in [
        m for m in list(sys.modules)
        if m == "vault_indexer" or m.startswith("vault_indexer.")
    ]:
        del sys.modules[mod]
    return tmp_path


# ---------------------------------------------------------------------------
# Tier 1 — unit tests on passes_scope()
# ---------------------------------------------------------------------------

def _reload_config(domain: str | None):
    """Force config reload under the given DOMAIN env (or unset)."""
    import os
    if domain is None:
        os.environ.pop("DOMAIN", None)
    else:
        os.environ["DOMAIN"] = domain
    if "vault_indexer.config" in sys.modules:
        del sys.modules["vault_indexer.config"]
    from vault_indexer import config
    return config


def test_finance_scope_rejects_fitness_paths(tmp_vault_with_registry):
    """DOMAIN=finance: paths under ``Videos/fitness`` etc are excluded."""
    cfg = _reload_config("finance")
    assert cfg.passes_scope("Books/graham/intro.md") is True
    assert cfg.passes_scope("Filings/AAPL/2026-q1.md") is True
    assert cfg.passes_scope("Videos/click-capital/2026-w19.md") is True
    # Cross-domain rejection
    assert cfg.passes_scope("Videos/fitness/galpin/intro.md") is False
    assert cfg.passes_scope("Books/fitness/attia-outlive/intro.md") is False
    assert cfg.passes_scope("Newsletters/fitness/some-author/2026-w19.md") is False
    assert cfg.passes_scope("Topics/fitness/strength.md") is False
    assert cfg.passes_scope("Videos/nutrition/satchin-panda/intro.md") is False
    assert cfg.passes_scope("Books/nutrition/intro.md") is False


def test_fitness_scope_includes_only_fitness_paths(tmp_vault_with_registry):
    """DOMAIN=fitness: only ``<Class>/fitness/...`` paths pass."""
    cfg = _reload_config("fitness")
    # Within scope
    assert cfg.passes_scope("Videos/fitness/galpin/intro.md") is True
    assert cfg.passes_scope("Books/fitness/attia-outlive/intro.md") is True
    assert cfg.passes_scope("Topics/fitness/strength.md") is True
    assert cfg.passes_scope("Newsletters/fitness/foo/2026-w19.md") is True
    # Out of scope
    assert cfg.passes_scope("Books/graham/intro.md") is False
    assert cfg.passes_scope("Filings/AAPL/2026-q1.md") is False
    assert cfg.passes_scope("Videos/nutrition/satchin-panda/intro.md") is False
    assert cfg.passes_scope("Videos/click-capital/2026-w19.md") is False


def test_nutrition_scope_includes_only_nutrition_paths(tmp_vault_with_registry):
    """DOMAIN=nutrition: only ``<Class>/nutrition/...`` paths pass."""
    cfg = _reload_config("nutrition")
    assert cfg.passes_scope("Videos/nutrition/satchin-panda/intro.md") is True
    assert cfg.passes_scope("Books/nutrition/healthy-eating/intro.md") is True
    assert cfg.passes_scope("Books/graham/intro.md") is False
    assert cfg.passes_scope("Videos/fitness/galpin/intro.md") is False


def test_no_domain_no_filter(tmp_vault_with_registry, monkeypatch):
    """DOMAIN unset + no INCLUDE/EXCLUDE env: legacy single-vault behaviour
    (everything passes). The coherence-check warning is the only signal of
    misconfiguration; passes_scope itself is permissive."""
    monkeypatch.delenv("INCLUDE_FOLDERS", raising=False)
    monkeypatch.delenv("EXCLUDE_FOLDERS", raising=False)
    cfg = _reload_config(None)
    assert cfg.passes_scope("Books/graham/intro.md") is True
    assert cfg.passes_scope("Videos/fitness/galpin/intro.md") is True
    assert cfg.passes_scope("Videos/nutrition/satchin-panda/intro.md") is True


def test_explicit_exclude_env_overrides_registry(tmp_vault_with_registry, monkeypatch):
    """Explicit EXCLUDE_FOLDERS env wins over yaml-derived scope. This is the
    documented escape hatch — operator can tighten or override per-instance."""
    monkeypatch.setenv("EXCLUDE_FOLDERS", "Books")  # block all Books
    cfg = _reload_config("finance")
    assert cfg.passes_scope("Books/graham/intro.md") is False
    assert cfg.passes_scope("Videos/click-capital/2026-w19.md") is True


def test_unknown_domain_no_filter(tmp_vault_with_registry):
    """DOMAIN=<unknown>: registry returns ((), ()) → no filter. The coherence
    check would warn; passes_scope itself stays permissive."""
    cfg = _reload_config("does-not-exist")
    assert cfg.passes_scope("Books/graham/intro.md") is True
    assert cfg.passes_scope("Videos/fitness/galpin/intro.md") is True


def test_empty_registry_no_filter(tmp_path, monkeypatch):
    """Missing or malformed registry: indexer falls through to no-filter
    (legacy single-vault behaviour). Important: the registry is the safety
    boundary — when it's broken, the indexer should NOT silently start
    excluding everything (over-correction). Permissive is the right default."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    # no _domains.yaml written
    for mod in [
        m for m in list(sys.modules)
        if m == "vault_indexer" or m.startswith("vault_indexer.")
    ]:
        del sys.modules[mod]
    cfg = _reload_config("finance")
    assert cfg.passes_scope("Anything/here.md") is True


# ---------------------------------------------------------------------------
# Tier 2 — integration test (model-dependent, skip-on-missing)
# ---------------------------------------------------------------------------

def _embedding_available() -> bool:
    home = Path.home() / ".cache" / "huggingface" / "hub"
    return (home / "models--BAAI--bge-large-en-v1.5").exists()


@pytest.mark.skipif(
    not _embedding_available(),
    reason="BGE model not in local HF cache — skip end-to-end ingest test",
)
def test_two_domain_ingest_no_cross_pollination(tmp_vault_with_registry, monkeypatch):
    """End-to-end: ingest mixed corpus into two caches; assert no leakage.

    1. Write finance content under `Books/graham/...` and fitness content
       under `Books/fitness/galpin/...`.
    2. Ingest with DOMAIN=finance, INDEXER_DB_PATH=cache-finance.db.
    3. Ingest with DOMAIN=fitness, INDEXER_DB_PATH=cache-fitness.db.
    4. Assert: finance cache has only Books/graham; fitness cache has only
       Books/fitness/galpin.
    """
    vault = tmp_vault_with_registry

    # Mixed corpus
    (vault / "Books" / "graham").mkdir(parents=True)
    (vault / "Books" / "graham" / "intro.md").write_text(
        "---\nkind: book_chapter\ntitle: Intelligent Investor Intro\nhorizon_months: 120\n---\n"
        "Margin of safety is the central concept of investment.\n",
        encoding="utf-8",
    )
    (vault / "Books" / "fitness").mkdir(parents=True)
    (vault / "Books" / "fitness" / "galpin").mkdir(parents=True)
    (vault / "Books" / "fitness" / "galpin" / "intro.md").write_text(
        "---\nkind: book_chapter\ntitle: Galpin Intro\nhorizon_months: 24\n---\n"
        "Strength training drives hypertrophy through mechanical tension.\n",
        encoding="utf-8",
    )

    # ---- Pass 1: finance ----
    finance_db = vault / ".indexer" / "cache-finance.db"
    monkeypatch.setenv("DOMAIN", "finance")
    monkeypatch.setenv("INDEXER_DB_PATH", str(finance_db))
    for mod in [
        m for m in list(sys.modules)
        if m == "vault_indexer" or m.startswith("vault_indexer.")
    ]:
        del sys.modules[mod]
    from vault_indexer import cache as _cache_f
    from vault_indexer import indexer as _indexer_f
    from vault_indexer.config import CONFIG as CFG_F
    con_f = _cache_f.init(CFG_F.db_path, CFG_F.embedding_dim)
    _indexer_f.full_rescan(con_f)

    paths_f = {row[0] for row in con_f.execute("SELECT path FROM vault_node")}
    assert any("Books/graham" in p for p in paths_f), (
        f"finance ingest missing graham content; got: {paths_f}"
    )
    assert not any("fitness" in p for p in paths_f), (
        f"finance ingest leaked fitness content: {paths_f}"
    )
    con_f.close()

    # ---- Pass 2: fitness ----
    fitness_db = vault / ".indexer" / "cache-fitness.db"
    monkeypatch.setenv("DOMAIN", "fitness")
    monkeypatch.setenv("INDEXER_DB_PATH", str(fitness_db))
    for mod in [
        m for m in list(sys.modules)
        if m == "vault_indexer" or m.startswith("vault_indexer.")
    ]:
        del sys.modules[mod]
    from vault_indexer import cache as _cache_g
    from vault_indexer import indexer as _indexer_g
    from vault_indexer.config import CONFIG as CFG_G
    con_g = _cache_g.init(CFG_G.db_path, CFG_G.embedding_dim)
    _indexer_g.full_rescan(con_g)

    paths_g = {row[0] for row in con_g.execute("SELECT path FROM vault_node")}
    assert any("fitness/galpin" in p for p in paths_g), (
        f"fitness ingest missing galpin content; got: {paths_g}"
    )
    assert not any(p.startswith("Books/graham") for p in paths_g), (
        f"fitness ingest leaked finance content: {paths_g}"
    )
    con_g.close()
