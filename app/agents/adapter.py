"""Agent engine adapter — interface + stub.

Mirrors the Kronos adapter pattern (`app/kronos/adapter.py`): a Protocol the
rest of the app codes against, plus a default stub that refuses to fabricate
decisions. The real engine (`app/agents/real_engine.py`) is swapped in at boot
only when ``AGENTS_ENABLED`` is set, exactly like ``activate_kronos()``.

Invariant: this boundary is the ONLY place the rest of the app touches the
TradingAgents library. Everything downstream sees a normalized
``AgentDecision`` and never imports langgraph / tradingagents directly.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Protocol

# Canonical stances. HOLD is a real, first-class outcome (no trade).
STANCES = ("BUY", "SELL", "HOLD")


@dataclass(frozen=True)
class AgentDecision:
    """Normalized output of one multi-agent run for one ticker."""

    ticker: str
    made_on: datetime.date
    stance: str  # one of STANCES
    engine: str = "tradingagents"
    engine_version: str = "stub"
    confidence: float | None = None  # 0..1 when the engine reports it
    rationale_md: str | None = None
    transcript_ref: str | None = None  # path/id to the raw debate, if persisted
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stance not in STANCES:
            raise ValueError(f"invalid stance {self.stance!r}; expected one of {STANCES}")


class AgentEngine(Protocol):
    """Contract for a multi-agent decision engine."""

    name: str

    async def decide(self, ticker: str, *, made_on: datetime.date) -> AgentDecision: ...


class StubAgentEngine:
    """Default engine. Refuses to produce real decisions — TradingAgents not wired.

    If ``settings.DEBUG_STUB`` is true, returns a deterministic synthetic
    decision so the service + routes can be exercised end-to-end without the
    heavy library or any LLM call. NEVER enable DEBUG_STUB in production.
    """

    name = "stub"

    async def decide(self, ticker: str, *, made_on: datetime.date) -> AgentDecision:
        from app.core.config import SETTINGS

        if SETTINGS.DEBUG_STUB:
            # Deterministic: map the ticker hash to a stance so tests are stable.
            stance = STANCES[sum(ord(c) for c in ticker) % 3]
            return AgentDecision(
                ticker=ticker.upper(),
                made_on=made_on,
                stance=stance,
                engine="tradingagents",
                engine_version="stub",
                confidence=0.5,
                rationale_md=f"_stub decision for {ticker.upper()}_",
                meta={"stub": True},
            )
        raise NotImplementedError(
            "Agent engine not integrated. Set AGENTS_ENABLED=true with the "
            "extras in requirements-agents.txt installed, or DEBUG_STUB=true "
            "for a synthetic decision."
        )


_engine: AgentEngine = StubAgentEngine()


def get_engine() -> AgentEngine:
    return _engine


def set_engine(engine: AgentEngine) -> None:
    """Test / integration hook — swap the active engine."""
    global _engine
    _engine = engine
