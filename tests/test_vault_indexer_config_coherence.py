"""Tests for ``vault_indexer.config._log_config_coherence``.

The coherence check warns (never crashes) when ``DOMAIN`` and
``INDEXER_DB_PATH`` disagree about which domain the operator is configuring.
Covers two failure modes:

  1. DOMAIN set + DB filename doesn't match ``cache-<domain>.db`` or legacy
     ``cache.db`` → warn (likely mis-configured plist).
  2. DOMAIN unset + DB filename matches ``cache-<slug>.db`` pattern → warn
     (operator probably forgot to set DOMAIN; indexer falls through to
     single-vault legacy scope).

Each test reloads the ``vault_indexer.config`` module under a fresh env so
the module-level ``CONFIG = Config()`` runs with the test's monkeypatched
environment and the ``_log_config_coherence(CONFIG)`` call emits the right
warning (or stays silent on coherent setups).
"""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

import pytest

# tools/ is not a package by default; stitch path so we can import.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture
def env_setup(tmp_path, monkeypatch):
    """Wipe the vault_indexer package from sys.modules so the next import
    picks up the test's env."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    for mod in [
        m for m in list(sys.modules)
        if m == "vault_indexer" or m.startswith("vault_indexer.")
    ]:
        del sys.modules[mod]
    return tmp_path


def _reload_config_and_capture(caplog):
    """Import ``vault_indexer.config`` fresh + capture WARNING records."""
    caplog.set_level(logging.WARNING, logger="vault-indexer.config")
    if "vault_indexer.config" in sys.modules:
        del sys.modules["vault_indexer.config"]
    from vault_indexer import config  # noqa: F401 — import triggers coherence check
    return [r for r in caplog.records if r.name == "vault-indexer.config"]


def test_coherent_finance_setup_no_warning(env_setup, monkeypatch, caplog):
    """DOMAIN=finance + INDEXER_DB_PATH=cache-finance.db → silent."""
    monkeypatch.setenv("DOMAIN", "finance")
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache-finance.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert warns == [], f"expected no warnings, got: {[r.message for r in warns]}"


def test_coherent_fitness_setup_no_warning(env_setup, monkeypatch, caplog):
    """DOMAIN=fitness + INDEXER_DB_PATH=cache-fitness.db → silent."""
    monkeypatch.setenv("DOMAIN", "fitness")
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache-fitness.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert warns == [], f"expected no warnings, got: {[r.message for r in warns]}"


def test_legacy_cache_db_allowed_with_domain(env_setup, monkeypatch, caplog):
    """DOMAIN=finance + INDEXER_DB_PATH=cache.db (legacy) → silent.

    The legacy name is intentionally accepted to avoid churning installs that
    pre-date the rename.
    """
    monkeypatch.setenv("DOMAIN", "finance")
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert warns == [], (
        "expected legacy cache.db to be silently accepted, got: "
        f"{[r.message for r in warns]}"
    )


def test_domain_db_mismatch_warns(env_setup, monkeypatch, caplog):
    """DOMAIN=finance + INDEXER_DB_PATH=cache-fitness.db → WARN."""
    monkeypatch.setenv("DOMAIN", "finance")
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache-fitness.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "config coherence" in msg
    assert "DOMAIN='finance'" in msg or "DOMAIN=\"finance\"" in msg
    assert "cache-fitness.db" in msg
    assert warns[0].levelno == logging.WARNING


def test_domain_unset_but_db_looks_domainy_warns(env_setup, monkeypatch, caplog):
    """DOMAIN unset + INDEXER_DB_PATH=cache-finance.db → WARN."""
    monkeypatch.delenv("DOMAIN", raising=False)
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache-finance.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "config coherence" in msg
    assert "DOMAIN env is unset" in msg
    assert "cache-finance.db" in msg
    assert "Set DOMAIN=finance" in msg


def test_unset_domain_and_legacy_db_silent(env_setup, monkeypatch, caplog):
    """DOMAIN unset + INDEXER_DB_PATH=cache.db → silent (pre-registry install)."""
    monkeypatch.delenv("DOMAIN", raising=False)
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert warns == [], (
        "pre-registry single-vault install should not warn; got: "
        f"{[r.message for r in warns]}"
    )


def test_experiment_db_name_with_domain_warns_softly(env_setup, monkeypatch, caplog):
    """DOMAIN=finance + INDEXER_DB_PATH=cache-experiment.db → WARN (soft).

    Ad-hoc experiment DBs are tolerated (the warning is non-blocking) but
    surfaced so the operator sees them in the launchd log.
    """
    monkeypatch.setenv("DOMAIN", "finance")
    monkeypatch.setenv(
        "INDEXER_DB_PATH",
        str(env_setup / ".indexer" / "cache-experiment.db"),
    )
    warns = _reload_config_and_capture(caplog)
    assert len(warns) == 1
    assert "cache-experiment.db" in warns[0].getMessage()
