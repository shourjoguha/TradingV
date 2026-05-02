# Roadmap — what's next

> Forward-looking. Phases 0-6 of the decision-tool roadmap shipped on 2026-04-27 — see [roadmap-shipped.md](roadmap-shipped.md). Currently no major phase in active build.

## Active

**M-3 — Wire hypotheses into Opportunities + Trades (next).** Phase 3 (stress-test endpoint) shipped 2026-05-02 — see [research.md](research.md) and [decisions/015](decisions/015-research-stress-test.md). `POST /v1/research/ask` bundles hypothesis + vault evidence + macro state, calls Claude with a tool-use schema constrained to `propose_invalidator_update`, writes the answer as markdown into `<vault>/Research/`. Operator approves via Obsidian checkbox; vault-indexer's `/promote` flow HTTP-calls TradingView's approve route. Weekly auto-stress per active hypothesis writes summaries into `_review-queue.md`. M-3 (per-hypothesis tagging on opportunities + trades, per-hypothesis P&L) is the next product-shaped step.

## Next candidates (not committed)

Order is approximate. Promotion to "Active" requires deliberation + plan. Most candidates derive from operator unlocks (see [backlog.md](backlog.md)) or tech debt triggers (see [tech_debt.md](tech_debt.md)).

| # | Candidate | Trigger | Estimate |
|---|---|---|---|
| 7 | Telegram bot setup + drift alert verification | Operator wants push notifications | ~5 min ([backlog.md](backlog.md) Unlock #1) |
| 8 | ~~OHLCV on-demand refresh in evaluator~~ | ✅ shipped 2026-04-30 ([decisions/010](decisions/010-self-healing-ohlcv-fetch.md)) | — |
| 8a | ~~Macro Workbench M-1 — Signal layer~~ | ✅ shipped 2026-04-30 ([macro.md](macro.md), [decisions/012](decisions/012-macro-workbench-storage-shape.md)) | — |
| 8b | ~~Macro Workbench M-2 — Hypothesis object + view registry~~ | ✅ shipped 2026-05-01 ([hypotheses.md](hypotheses.md), [views.md](views.md), [decisions/013](decisions/013-hypothesis-object.md)) | — |
| 8b.1 | ~~Phase 2 — Vault + indexer sidecar~~ | ✅ shipped 2026-05-02 ([vault.md](vault.md), [decisions/014](decisions/014-vault-indexer.md)) | — |
| 8b.2 | ~~Phase 3 — Stress-test endpoint~~ | ✅ shipped 2026-05-02 ([research.md](research.md), [decisions/015](decisions/015-research-stress-test.md)) | — |
| 8b.3 | Phase 3.1 — Synthesis mode (`/research/digest`) | After Phase 3 stress-test loop in regular use | ~4-6 hrs |
| 8b.4 | Phase 3.2 — Additional action kinds (`cancel_hypothesis`, `create_opportunity`) | After 20+ stress-tests run; operator wants more from one query | TBD |
| 8b.5 | Phase 3.3 — Telegram digest of unread research answers | If Phase 3 auto-stress files go unread for 2-3 weeks | ~1 hr |
| 8b.6 | Phase 3.4 — Cross-hypothesis stress (one query, multiple theses) | After single-thesis stress-test feels routine | TBD |
| 8b.7 | Phase 3.5 — Multi-LLM cross-check (Claude + GPT) | Only if Claude proposals disagree with operator gut > 30% of the time | TBD |
| 8b.8 | **Phase 3.7 — Research UI v1 (single-turn)** — `/research` page in the React app: input box, hypothesis-scope chip selector, verdict + evidence + proposed-action card, confirm-modal Approve, paginated history. AskResponse extended with structured `evidence` field. | Operator brainstorm 2026-05-02; markdown-only path is friction even with auto-stress | ~6-8 hrs (full plan: [plans/phase-3.7-research-ui-single-turn.md](plans/phase-3.7-research-ui-single-turn.md)) |
| 8b.9 | **Phase 3.8 — Research UI v2 (threading)** — multi-turn conversation per hypothesis. `research_queries` gains `thread_id`; bundle assembler folds prior turns; "New thread" UI. | After Phase 3.7 in regular use AND operator hits "I asked the same hypothesis 3+ times this week and wished the answers knew about each other" | TBD (direction notes: [plans/phase-3.8-research-ui-threading.md](plans/phase-3.8-research-ui-threading.md)) |
| 8b.10 | ~~Free-form open chat over the corpus~~ | OUT OF SCOPE — operator decided 2026-05-02 to use the Claude API directly when they want open-ended discussion. Claude can read this stack as context AND perform outside research; building a generic chat UI inside TradingView would duplicate that without differentiation. | — |
| 8c | **Macro Workbench M-3 — Wire into Opportunities + Trades** (per-hypothesis tagging on rows; per-hypothesis P&L) | After M-2 + at least 3 active hypotheses | ~1-2 days |
| 8d | ~~Macro Workbench M-4 — `POST /v1/research/ask` LLM endpoint~~ | Subsumed by Phase 3 (8b.2) | — |
| 8e | Macro Workbench M-5 — 13F + Form-4 ingestion | After Phase 3 ships and is in use | TBD |
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
