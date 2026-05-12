# ADR-007: Hardcoded opportunity rules over a DSL

**Date**: 2026-04-27
**Status**: Accepted

## Context

Phase 3.1 needed a way to convert Kronos predictions into BUY/SELL signals. Two paths: a small DSL ("rules engine") that the operator could tune in YAML/JSON, vs. hardcoded rules in Python.

## Options considered

- **A · Hardcoded rules** — 3-5 Python functions in `app/opportunities/rules.py`, each `RuleInput → Optional[RuleHit]`. Tweak = code change + redeploy.
- **B · DSL (e.g. simpleeval, pandas.query, custom AST)** — operator edits rules without redeploying. More flexible.
- **C · Visual rule builder UI** — overkill for v1.

## Decision

**Hardcoded.** Reasons:
- Three rules cover the common cases (R1: BUY +2%/5d, R2: SELL -2%/5d, R3: BUY +5%/10d). Adding a fourth is a 5-line PR.
- We don't yet know what the right thresholds are — the rules will change as accuracy data accumulates. Hardcoding makes the changes explicit + auditable.
- A DSL is a footgun before you know what you're tuning.
- `UNIQUE(prediction_id, rule_id)` enforces idempotency cleanly with hardcoded rule IDs.

## Trigger to revisit

- Operator tweaks rule thresholds > once a week for > 4 weeks (signal that flexibility is wanted).
- Need for per-ticker rule customization (e.g. AAPL uses +3%/5d, TSLA uses +5%/3d).
- Multiple rule families that share structure (e.g. moving-average crossovers, Bollinger bands).

## Files affected

- `app/opportunities/rules.py` (rule functions + `RULES` list)
- `app/opportunities/service.py` (`evaluate(inp)` calls each rule)
- `tests/` — rules are unit-testable as pure functions

## Cross-references

- [opportunities.md](../modules/opportunities.md) — rule engine doc
- [decisions/000-template.md](000-template.md) — ADR template
