# Archive

Stale handoffs + superseded design docs. Kept for context-audit (so an
agent can trace why decisions landed where they did) but not part of the
active reading paths.

## Contents

| File | Status |
|---|---|
| [session-handoff-2026-05-01.md](session-handoff-2026-05-01.md) | Superseded by [`../status/roadmap-shipped.md`](../status/roadmap-shipped.md) entries from 2026-05-01 onward |
| [session-handoff-2026-05-02.md](session-handoff-2026-05-02.md) | Superseded by [`../status/roadmap-shipped.md`](../status/roadmap-shipped.md) entries from 2026-05-02 onward |

## When to read

- Investigating why a phase took the shape it did → check the handoff that bracketed its kickoff
- Auditing a long-running tradeoff → trace from a recent ADR (`../decisions/`) back to the handoff that surfaced the question

## When NOT to read

- Onboarding a new context — read [`../status/roadmap-shipped.md`](../status/roadmap-shipped.md) instead. The handoffs are duplicated there in cleaner form.
- Planning new work — handoffs reflect a moment in time, not the current state.

## Adding to the archive

Move stale top-level docs here when:
- Their content is superseded by a more current doc
- They're a session-specific snapshot that won't be edited again
- Removing them would lose useful "why we got here" context

Don't archive ADRs (they live forever in `../decisions/` by convention) or
shipped retros (they live forever in `../status/roadmap-shipped.md`).
