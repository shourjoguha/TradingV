"""Tests for app.core.schema_check — the boot-time drift WARN.

The check must:
  - log WARN when on-disk revision != DB revision
  - log WARN when alembic_version is missing/empty
  - stay silent (no log) when they match
  - never raise — this is a soft check
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import schema_check


@pytest.mark.asyncio
async def test_silent_when_no_migrations_dir(monkeypatch, caplog):
    """Outside the repo (no migrations dir) we don't warn."""
    monkeypatch.setattr(schema_check, "latest_revision_on_disk", lambda *_: None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    with caplog.at_level(logging.WARNING, logger="app.core.schema_check"):
        await schema_check.warn_if_drift(engine)
    assert all("schema" not in rec.message for rec in caplog.records)
    await engine.dispose()


@pytest.mark.asyncio
async def test_warn_when_alembic_version_missing(monkeypatch, caplog):
    monkeypatch.setattr(schema_check, "latest_revision_on_disk", lambda *_: "0042")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    with caplog.at_level(logging.WARNING, logger="app.core.schema_check"):
        await schema_check.warn_if_drift(engine)
    assert any("alembic_version table missing" in rec.message for rec in caplog.records)
    await engine.dispose()


@pytest.mark.asyncio
async def test_warn_on_mismatch(monkeypatch, caplog):
    monkeypatch.setattr(schema_check, "latest_revision_on_disk", lambda *_: "0042")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE alembic_version (version_num TEXT NOT NULL)"))
        await conn.execute(text("INSERT INTO alembic_version VALUES ('0040')"))
    with caplog.at_level(logging.WARNING, logger="app.core.schema_check"):
        await schema_check.warn_if_drift(engine)
    assert any("DB at revision 0040; latest on disk is 0042" in rec.message for rec in caplog.records)
    await engine.dispose()


@pytest.mark.asyncio
async def test_silent_on_match(monkeypatch, caplog):
    monkeypatch.setattr(schema_check, "latest_revision_on_disk", lambda *_: "0042")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE alembic_version (version_num TEXT NOT NULL)"))
        await conn.execute(text("INSERT INTO alembic_version VALUES ('0042')"))
    with caplog.at_level(logging.WARNING, logger="app.core.schema_check"):
        await schema_check.warn_if_drift(engine)
    assert all("revision" not in rec.message for rec in caplog.records)
    await engine.dispose()


def test_latest_revision_on_disk_against_real_repo():
    """Sanity check — finds the actual highest revision in the repo's
    migrations/versions/ dir."""
    rev = schema_check.latest_revision_on_disk()
    # As of Phase 2 ship, head is 0022. Test asserts >= 0022 so it doesn't
    # break when future migrations land.
    assert rev is not None
    assert rev >= "0022"
