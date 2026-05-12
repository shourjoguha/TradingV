"""In-process runtime registry of live loop handles.

Lifespan startup populates this dict; routes mutate it (manual fire, abort).
Cleared on process restart — that's fine, the next lifespan startup
re-registers everything.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


FireFn = Callable[[], Awaitable[None]]


@dataclass
class LoopHandle:
    loop_id: str
    stop_event: Optional[asyncio.Event] = None
    task: Optional[asyncio.Task] = None
    fire_now: Optional[FireFn] = None
    last_fire_attempt_at: float = 0.0  # monotonic
    enabled: bool = True


_HANDLES: dict[str, LoopHandle] = {}

# Default 30s server-side debounce on /fire so triple-clicks return 429.
FIRE_DEBOUNCE_SECONDS = 30.0


def register(handle: LoopHandle) -> None:
    _HANDLES[handle.loop_id] = handle


def get(loop_id: str) -> Optional[LoopHandle]:
    return _HANDLES.get(loop_id)


def all_handles() -> dict[str, LoopHandle]:
    return dict(_HANDLES)


def clear() -> None:
    """Test hook — wipes the registry between cases."""
    _HANDLES.clear()


def fire_debounce_remaining(handle: LoopHandle) -> float:
    """Seconds remaining on the fire-now cooldown. 0 if cleared."""
    elapsed = time.monotonic() - handle.last_fire_attempt_at
    remaining = FIRE_DEBOUNCE_SECONDS - elapsed
    return max(0.0, remaining)


def stamp_fire(handle: LoopHandle) -> None:
    handle.last_fire_attempt_at = time.monotonic()
