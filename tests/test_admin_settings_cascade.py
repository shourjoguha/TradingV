"""Settings cascade — DB > env > hardcoded default."""
from __future__ import annotations

import os

import pytest

from app.admin import service as _svc


@pytest.mark.asyncio
async def test_default_when_nothing_set(client):
    # Clean slate — no DB row, no env var. Falls through to hardcoded default.
    val = await _svc.get_setting("anthropic.enabled")
    assert val is True


@pytest.mark.asyncio
async def test_env_var_overrides_default(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "false")
    val = await _svc.get_setting("anthropic.enabled")
    assert val is False


@pytest.mark.asyncio
async def test_db_overrides_env(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "false")
    await _svc.set_setting("anthropic.enabled", True)
    val = await _svc.get_setting("anthropic.enabled")
    # DB row wins.
    assert val is True


@pytest.mark.asyncio
async def test_caller_default_used_when_no_other_source(client):
    val = await _svc.get_setting("nonexistent.key", default=42)
    assert val == 42


@pytest.mark.asyncio
async def test_set_setting_upsert(client):
    await _svc.set_setting("anthropic.monthly_cap_usd", 10.0)
    val = await _svc.get_setting("anthropic.monthly_cap_usd")
    assert val == 10.0
    # Update.
    await _svc.set_setting("anthropic.monthly_cap_usd", 25.0)
    val = await _svc.get_setting("anthropic.monthly_cap_usd")
    assert val == 25.0


@pytest.mark.asyncio
async def test_kill_switch_via_explicit_disable(client):
    await _svc.set_setting("anthropic.enabled", False)
    assert await _svc.anthropic_kill_switch_active() is True


@pytest.mark.asyncio
async def test_kill_switch_via_cap_breach(client, monkeypatch):
    # Cap = 0.0001 → any spend trips it. Mock the spend to return 0.5.
    await _svc.set_setting("anthropic.enabled", True)
    await _svc.set_setting("anthropic.monthly_cap_usd", 0.0001)

    async def _fake_spend():
        return 0.5

    monkeypatch.setattr(_svc, "month_to_date_anthropic_spend_usd", _fake_spend)
    assert await _svc.anthropic_kill_switch_active() is True


@pytest.mark.asyncio
async def test_kill_switch_clear_when_under_cap(client, monkeypatch):
    await _svc.set_setting("anthropic.enabled", True)
    await _svc.set_setting("anthropic.monthly_cap_usd", 5.0)

    async def _fake_spend():
        return 0.0

    monkeypatch.setattr(_svc, "month_to_date_anthropic_spend_usd", _fake_spend)
    assert await _svc.anthropic_kill_switch_active() is False
