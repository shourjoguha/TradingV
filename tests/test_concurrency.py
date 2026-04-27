"""Concurrency-gate semantics — kept as belt-and-braces under Tier-1 queue.

Under the Tier-1 submit queue, the route layer no longer hits the slot
gate (queue accepts every request → 202). The slot gate inside
``service.submit_run`` stays as belt-and-braces — see
[.claude/tech_debt.md](../.claude/tech_debt.md) for the cleanup trigger.

These tests now drive ``service.submit_run`` directly to exercise the
gate, since the route doesn't surface 429 anymore.
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
async def test_second_concurrent_service_call_gets_at_capacity(client, monkeypatch):
    """Direct service-level: two concurrent submit_runs, second hits gate.

    The route used to surface this as 429; now the queue serializes so
    this never fires from a normal request path. Kept as a unit test of
    the gate itself.
    """
    release = asyncio.Event()

    async def slow_process(job_id, *, horizon_bars):
        await release.wait()

    monkeypatch.setattr(service, "_process_job", slow_process)

    async def submit():
        return await service.submit_run(
            tickers=["AAPL"],
            intervals=["1d"],
            model_ids=["kronos_base"],
        )

    first = asyncio.create_task(submit())
    await asyncio.sleep(0.05)  # let first acquire slot

    with pytest.raises(concurrency.AtCapacityError):
        await service.submit_run(
            tickers=["AAPL"],
            intervals=["1d"],
            model_ids=["kronos_base"],
        )

    release.set()
    await first

    # After first completes, a third call succeeds.
    r3 = await service.submit_run(
        tickers=["AAPL"],
        intervals=["1d"],
        model_ids=["kronos_base"],
    )
    assert r3 is not None


@pytest.mark.asyncio
async def test_gate_releases_on_process_error(client, monkeypatch):
    """Even if _process_job blows up, the slot must be released."""
    async def boom(job_id, *, horizon_bars):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_process_job", boom)

    with pytest.raises(RuntimeError, match="boom"):
        await service.submit_run(
            tickers=["AAPL"],
            intervals=["1d"],
            model_ids=["kronos_base"],
        )

    # Gate must be clear regardless of the error.
    assert concurrency.in_flight() == 0
