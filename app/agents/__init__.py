"""Agents module — a multi-agent LLM decision engine that runs *alongside*
Kronos, not in place of it.

Design (see `.claude/modules/agents.md`):
- TradingV's primary lane is Kronos forecast -> rule signals -> opportunities.
- This module adds a SECOND, independent lane: a multi-agent "trading firm"
  (TauricResearch/TradingAgents) that debates a ticker and emits a discrete
  BUY/SELL/HOLD ``AgentDecision``. The two lanes do not depend on each other.
- Ships dark: nothing runs unless ``AGENTS_ENABLED=true`` (mirrors the Kronos
  optional-engine pattern: stub by default, real impl lazy-loaded at boot).
"""
