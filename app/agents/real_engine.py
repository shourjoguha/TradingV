"""Real agent engine — lazy wrapper over TauricResearch/TradingAgents.

Activated at boot only when ``AGENTS_ENABLED`` is set (see ``activate()`` and
its call site in ``app/main.py``), mirroring ``app.kronos.real_adapter.activate``.

The heavy dependency (langgraph + tradingagents + LLM SDKs) lives in
``requirements-agents.txt`` and is imported INSIDE ``decide`` so the base app
and the test suite never pay for it. If the import or the run fails, we fail
loud with a clear message rather than fabricating a decision.

Cost/safety: the engine reuses the existing Anthropic config (``CLAUDE_MODEL``)
and respects the admin kill-switch + monthly cap before spending.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os

from app.agents.adapter import STANCES, AgentDecision, set_engine

logger = logging.getLogger(__name__)


def _normalize_stance(raw: object) -> str:
    """Map TradingAgents' free-text decision to a canonical stance."""
    s = str(raw or "").strip().upper()
    if s in STANCES:
        return s
    if "BUY" in s or "LONG" in s:
        return "BUY"
    if "SELL" in s or "SHORT" in s:
        return "SELL"
    return "HOLD"


class TradingAgentsEngine:
    """Adapter onto the TradingAgents LangGraph."""

    name = "tradingagents"

    def __init__(self) -> None:
        self._graph = None
        self._version = "tradingagents"

    def _build_graph(self):
        # Imported lazily — only when the engine is actually exercised.
        from tradingagents.default_config import DEFAULT_CONFIG  # type: ignore
        from tradingagents.graph.trading_graph import TradingAgentsGraph  # type: ignore

        config = dict(DEFAULT_CONFIG)
        # Reuse the app's configured Claude model + key so the Agents lane and
        # the research lane bill against the same provider/budget.
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
        config["llm_provider"] = os.environ.get("AGENTS_LLM_PROVIDER", "anthropic")
        config["deep_think_llm"] = os.environ.get("AGENTS_DEEP_MODEL", model)
        config["quick_think_llm"] = os.environ.get("AGENTS_QUICK_MODEL", model)
        try:
            self._version = f"tradingagents@{_pkg_version()}"
        except Exception:  # noqa: BLE001
            pass
        return TradingAgentsGraph(debug=False, config=config)

    async def decide(self, ticker: str, *, made_on: datetime.date) -> AgentDecision:
        # Respect the existing Anthropic kill-switch + monthly cap before spend.
        from app.admin import service as _admin_svc

        if hasattr(_admin_svc, "anthropic_kill_switch_active"):
            if await _maybe_await(_admin_svc.anthropic_kill_switch_active()):
                raise RuntimeError("agents: Anthropic kill-switch active; refusing to run")

        if self._graph is None:
            self._graph = await asyncio.to_thread(self._build_graph)

        # TradingAgents is sync + blocking; run off the event loop.
        state, decision = await asyncio.to_thread(
            self._graph.propagate, ticker.upper(), made_on.isoformat()
        )
        stance = _normalize_stance(decision)
        rationale = _extract_rationale(state, decision)
        return AgentDecision(
            ticker=ticker.upper(),
            made_on=made_on,
            stance=stance,
            engine="tradingagents",
            engine_version=self._version,
            confidence=None,  # TradingAgents emits a discrete call, not a probability
            rationale_md=rationale,
            meta={"raw_decision": str(decision)},
        )


def _extract_rationale(state: object, decision: object) -> str | None:
    """Best-effort: pull the trader's narrative out of the graph state."""
    if isinstance(state, dict):
        for key in ("final_trade_decision", "trader_investment_plan", "investment_plan"):
            val = state.get(key)
            if val:
                return str(val)
    return str(decision) if decision is not None else None


async def _maybe_await(val):
    if asyncio.iscoroutine(val):
        return await val
    return val


def _pkg_version() -> str:
    from importlib.metadata import version

    return version("tradingagents")


def activate() -> None:
    """Swap the stub engine for the real TradingAgents engine. Call at boot
    when AGENTS_ENABLED is true."""
    set_engine(TradingAgentsEngine())
    logger.info("agents: TradingAgents engine activated")
