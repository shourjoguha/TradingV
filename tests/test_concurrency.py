"""Concurrency-gate semantics: second concurrent submit must get 429.

We don't need the adapter to actually take time — we patch `_process_job`
with a blocker so the first submit holds the slot while the second one
hits the gate.
"""
from __future__ import annotations

import asyncio

import pytest

from app.analysis import concurrency, service

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def _reset_gate():
    concurrency.reset_for_tests(limit=1)
    yield
    concurrency.reset_for_tests(limit=1)


@pytest.mark.asyncio
async def test_second_concurrent_submit_gets_429(client, monkeypatch):
    release = asyncio.Event()

    async def slow_process(job_id, *, horizon_bars):
        await release.wait()

    monkeypatch.setattr(service, "_process_job", slow_process)

    body = {"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_base"]}

    async def submit():
        return await client.post("/v1/analysis/run", headers=HEADERS, json=body)

    # Start two submits concurrently.
    first = asyncio.create_task(submit())
    # Give the first one a chance to acquire the slot.
    await asyncio.sleep(0.05)
    second = asyncio.create_task(submit())

    # Second should 429 fast while first is still blocked.
    r2 = await second
    assert r2.status_code == 429
    assert r2.json()["detail"] == "at_capacity"

    # Release the first.
    release.set()
    r1 = await first
    assert r1.status_code == 200

    # Third request after first completes should succeed.
    r3 = await submit()
    assert r3.status_code == 200


@pytest.mark.asyncio
async def test_gate_releases_on_process_error(client, monkeypatch):
    """Even if _process_job blows up, the slot must be released."""
    async def boom(job_id, *, horizon_bars):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_process_job", boom)

    body = {"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_base"]}

    with pytest.raises(RuntimeError, match="boom"):
        await client.post("/v1/analysis/run", headers=HEADERS, json=body)

    # Gate must be clear regardless of the error.
    assert concurrency.in_flight() == 0
