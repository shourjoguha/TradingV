"""Process-wide concurrency gate for Kronos analysis jobs.

v1 backpressure contract: `submit_run` does a race-free check-and-increment;
if we're already at `MAX_CONCURRENT_JOBS` in-flight the HTTP layer returns
429 `at_capacity` instead of queueing. No queue, no waiting. Revisit when
we introduce arq/Redis.

State is module-level so it survives across requests in the same process.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from app.core.config import SETTINGS


class AtCapacityError(RuntimeError):
    """Raised when all concurrency slots are taken."""


_lock = asyncio.Lock()
_in_flight = 0
_limit = SETTINGS.MAX_CONCURRENT_JOBS


def reset_for_tests(limit: int | None = None) -> None:
    """Rebuild the gate. Tests use this to set small limits + clear state."""
    global _in_flight, _limit, _lock
    _in_flight = 0
    _limit = limit if limit is not None else SETTINGS.MAX_CONCURRENT_JOBS
    _lock = asyncio.Lock()


def in_flight() -> int:
    return _in_flight


@asynccontextmanager
async def acquire_slot():
    """Race-free non-blocking acquire. Raises AtCapacityError if full."""
    global _in_flight
    async with _lock:
        if _in_flight >= _limit:
            raise AtCapacityError("analysis capacity exhausted")
        _in_flight += 1
    try:
        yield
    finally:
        async with _lock:
            _in_flight -= 1
