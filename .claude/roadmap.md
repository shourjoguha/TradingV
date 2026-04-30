# Roadmap — what's next

> Forward-looking. Phases 0-6 of the decision-tool roadmap shipped on 2026-04-27 — see [roadmap-shipped.md](roadmap-shipped.md). Currently no major phase in active build.

## Active

**Macro Workbench M-2 (next).** M-1 signal layer shipped 2026-04-30 (38 symbols cached, `/v1/macro/{series,ratio,refresh}` live, daily ingestion loop running). M-2 plans the hypothesis object + view registry — see [`plans/M-2-hypothesis-object.md`](plans/M-2-hypothesis-object.md) outline. Gated on operator promotion (no hard prerequisites — five real hypothesis drafts already on disk under [`hypotheses/draft/`](hypotheses/draft/)).

## Next candidates (not committed)

Order is approximate. Promotion to "Active" requires deliberation + plan. Most candidates derive from operator unlocks (see [backlog.md](backlog.md)) or tech debt triggers (see [tech_debt.md](tech_debt.md)).

| # | Candidate | Trigger | Estimate |
|---|---|---|---|
| 7 | Telegram bot setup + drift alert verification | Operator wants push notifications | ~5 min ([backlog.md](backlog.md) Unlock #1) |
| 8 | ~~OHLCV on-demand refresh in evaluator~~ | ✅ shipped 2026-04-30 ([decisions/010](decisions/010-self-healing-ohlcv-fetch.md)) | — |
| 8a | ~~Macro Workbench M-1 — Signal layer~~ | ✅ shipped 2026-04-30 ([macro.md](macro.md), [decisions/012](decisions/012-macro-workbench-storage-shape.md)) | — |
| 8b | **Macro Workbench M-2 — Hypothesis object + view registry** (schema + 5 seeded views + CRUD + UI) | After M-1 | ~2-3 days |
| 8c | **Macro Workbench M-3 — Wire into Opportunities + Trades** (per-hypothesis tagging on rows; per-hypothesis P&L) | After M-2 + at least 3 active hypotheses | ~1-2 days |
| 8d | **Macro Workbench M-4 — `POST /v1/research/ask` LLM endpoint** (view-scoped DB context; Anthropic API) | After M-3; the unique-wedge layer | ~1-2 days |
| 8e | Macro Workbench M-5 — 13F + Form-4 ingestion | After M-4 ships and is in use | TBD |
| 8f | Macro Workbench M-6 — Hypothesis backtest engine | After M-5 + > 6 closed trades tagged with hypotheses | TBD |
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
