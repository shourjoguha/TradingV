# Status

Living state of the project. These files change frequently and capture the
**current** working set + recent history. Skim before kicking off new work
so you don't propose something already shipped, deferred, or known-broken.

## Index

| File | Purpose | Update frequency |
|---|---|---|
| [roadmap.md](roadmap.md) | What's next — forward-looking plan list. Append new phases here before kicking them off. | per-phase |
| [roadmap-shipped.md](roadmap-shipped.md) | What's already shipped — append-only retro log (one ¶ per phase). The most recent ~10 entries are usually relevant. | per-phase |
| [backlog.md](backlog.md) | Deferred features + known gaps + operator unlocks (e.g. "Telegram bot config pending"). | per-discovery |
| [tech_debt.md](tech_debt.md) | Code cruft knowingly left in shipped code, with the trigger that would justify revisiting. | per-shipped-phase |

## Reading order

For a fresh agent picking up the project:

1. **roadmap-shipped.md** (last ~10 entries) — what's been built recently
2. **roadmap.md** — what's queued
3. **backlog.md** — what's been seen but deferred
4. **tech_debt.md** — what's broken-on-purpose

## Conventions

- **Append-only retros** in `roadmap-shipped.md`. Each entry has a date prefix and a 1-3 paragraph summary. Don't rewrite history.
- **Backlog status markers**: `[OPEN]`, `[RESOLVED YYYY-MM-DD]`, `[DEFERRED]`, `[OPERATOR-UNLOCK]`. RESOLVED entries stay for audit; tag with the resolution PR/commit.
- **Tech-debt entries** must include a **trigger** for revisiting (e.g. "revisit when yfinance breaks at the library level, not per-symbol 404s").

## See also

- [`../guides/principles.md`](../guides/principles.md) — north-star principles that shape what goes in roadmap vs backlog
- [`../decisions/`](../decisions/) — ADRs explain why specific tradeoffs were made
- [`../plans/`](../plans/) — detailed phase plans authored before execution
- [`../../CLAUDE.md`](../../CLAUDE.md) — top-level reading paths
