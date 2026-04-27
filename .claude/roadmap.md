# Roadmap — what's next

> Forward-looking. Phases 0-6 of the decision-tool roadmap shipped on 2026-04-27 — see [roadmap-shipped.md](roadmap-shipped.md). Currently no major phase in active build.

## Active

_(Empty — last sprint completed.)_

## Next candidates (not committed)

Order is approximate. Promotion to "Active" requires deliberation + plan. Most candidates derive from operator unlocks (see [backlog.md](backlog.md)) or tech debt triggers (see [tech_debt.md](tech_debt.md)).

| # | Candidate | Trigger | Estimate |
|---|---|---|---|
| 7 | Telegram bot setup + drift alert verification | Operator wants push notifications | ~5 min ([backlog.md](backlog.md) Unlock #1) |
| 8 | OHLCV on-demand refresh in evaluator | Accuracy dashboard stays empty after 1 week of scheduled runs | ~30 min ([backlog.md](backlog.md) Unlock #2) |
| 9 | Concurrency-gate removal | Queue runs cleanly for 4 weeks with zero `acquire_slot` failures | ~30 min ([tech_debt.md](tech_debt.md)) |
| 10 | schedule_config column drop (`pending_run`, `retry_minutes`) | Bundled with the next schedule_config schema change | ~15 min ([tech_debt.md](tech_debt.md)) |
| 11 | Tier-2 queue (Redis + arq) | Queue depth > 5 sustained OR GPU inference lands | ~1-2 days ([tech_debt.md](tech_debt.md)) |
| 12 | Options strategy generator (uses Phase 6 IV data) | Operator-initiated; needs plan + design | TBD |
| 13 | lightweight-charts v4 → v5 upgrade | Want crosshair sync, drawing tools | ~2h ([backlog.md](backlog.md)) |
| 14 | E2E tests via Playwright MCP | Frontend regressions cost more than the test setup | TBD |

## Principles that gate the sequence

(Same ones as last sprint; see [principles.md](principles.md) for the full list.)

1. Trust before action — observability work goes before action work.
2. Cheap reversibility — every phase tagged + snapshotted.
3. Single user — no premature generality.
4. External channels stay external — no news/policy ingestion.

## How to start a new phase

1. Read [principles.md](principles.md) — confirm the new phase doesn't violate them.
2. `/plan` — deliberate, get sign-off.
3. Snapshot if the phase touches durable state (DB schema or Railway env).
4. Build, test, doc, commit.
5. Add to `roadmap-shipped.md` retrospective notes when done.

## How to deprioritize

If a "Next candidate" gets stale (trigger fires but nothing happens for > 4 weeks), demote it to [backlog.md](backlog.md) so it doesn't pretend to be on the roadmap.
