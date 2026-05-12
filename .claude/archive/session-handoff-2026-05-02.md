# Session handoff — 2026-05-02 (supersedes 2026-05-01)

> **Next-session quick-start:** read this file, then `git log --oneline e1b3f21..HEAD` for the 14 commits since the last handoff. Active plan + open questions at the bottom. State is good as of HEAD = `25e7f91`.

## Where things stand

- **Tree clean, all pushed to origin/main.** Last commit `25e7f91` (Phase 3.7 Research UI v1).
- **Backend tests:** 341/341 green.
- **TypeScript:** `tsc --noEmit` clean.
- **Postgres** at migration head `0023_research_queries`. **Lifespan no longer calls `Base.metadata.create_all`** — schema is migration-driven (see ADR-013/014, fix in `d6b4cb6`); a boot-time schema-drift WARN runs from `app/core/schema_check.warn_if_drift`.
- **Backend** (port 8000) was running for the operator earlier; the background task was killed during this compress step. Restart with the standard `uvicorn` + `.env.laptop` command if needed.
- **Vault-indexer sidecar** runs separately on port 8001 over SQLite + sqlite-vec, against `~/Documents/knowledge-vault/`. See `tools/vault_indexer/` and `.claude/vault.md`.

## What shipped between last handoff and now (14 commits)

| # | Commit | Subject |
|---|---|---|
| 1 | `663048a` | M-2 hypothesis object + view registry; bundled UI fixes |
| 2 | `b56fde0` | Ops: seed M-2 + DSL patch on laptop; backlog the create_all wart |
| 3 | `89c1ab3` | Phase 2 — knowledge vault + indexer sidecar |
| 4 | `d6b4cb6` | Remove `Base.metadata.create_all` from lifespan; add boot-time schema-drift WARN |
| 5 | `2fe5ddf` | Phase 3 — research stress-test endpoint + Claude tool-use + vault-tick approval |
| 6 | `16acd7e` | Vault-indexer source breadcrumb in ingest frontmatter |
| 7 | `7251435` | Test gate: `DISABLE_LIFESPAN_BACKGROUND_TASKS` env flag |
| 8 | `e593b9d` | Re-evaluate vault-indexer stack vs LightRAG + Gemini; no change |
| 9 | `a61bac0` | Layout-aware PDF chapter detection in ingest |
| 10 | `1cd9acf` | Vault-indexer fix: unpack `similar_to_node` result dicts |
| 11 | `d5df466` | Vault-indexer runbook + persistence note |
| 12 | `9b6b94d` | Split research UI phase into 3.7 (single-turn) + 3.8 (threading); mark open-chat OOS |
| 13 | `ad5ab35` | Prep for next-session pickup of Phase 3.7 |
| 14 | `25e7f91` | Phase 3.7 — Research UI v1 (single-turn) |

## Active phase / on-deck

| State | Phase | Notes |
|---|---|---|
| **Just shipped** | Phase 3.7 — Research UI v1 (single-turn) | `/research` page wired into React; AnswerCard with verdict + flat evidence list + proposed-action card; confirm-modal Approve; status-filtered history. Backend `AskResponse` + `ResearchQueryRead` extended with `evidence` + `macro_state` + `proposed_action` for single-call render. Plan: [`plans/phase-3.7-research-ui-single-turn.md`](../plans/phase-3.7-research-ui-single-turn.md). |
| **On deck (gated)** | Phase 3.8 — Research UI v2 (threading) | Multi-turn conversation per hypothesis. `research_queries` gains `thread_id`; bundle assembler folds prior turns; "New thread" UI. Trigger: operator hits "I asked the same hypothesis 3+ times this week and wished the answers knew about each other". Plan stub: [`plans/phase-3.8-research-ui-threading.md`](../plans/phase-3.8-research-ui-threading.md). |
| **Out of scope** | Free-form open chat over the corpus | Operator decided 2026-05-02: use Claude API directly; building generic chat inside TradingView would duplicate that. |
| **After 3.8** | M-3 — Wire hypotheses into Opportunities + Trades | Per-hypothesis tagging on rows + per-hypothesis P&L. ~1-2 days. |

Other candidates in [.claude/roadmap.md](../status/roadmap.md) — synthesis mode (8b.3), additional action kinds (8b.4), Telegram digest (8b.5), cross-hypothesis stress (8b.6), multi-LLM (8b.7), 13F+Form-4 (8e), backtest engine (8f).

## Hypotheses (in DB now, not just markdown)

M-2 ingested all 6 drafts on 2026-05-01. First force-fire of the lifespan tick: `{evaluated: 6, expired: 0, invalidated: 0}` — all 6 active.

| slug | TTL | Type |
|---|---|---|
| latam-breakout-36m | 30mo | regime (parent) |
| latam-breakout-18m | 6mo | tactical (child of 36m) |
| saas-mission-critical-2x-18m | 18mo | single_name |
| btc-bottom-3m | 6mo | tactical (precondition) |
| btc-rally-24m | 30mo | regime (depends on bottom-3m) |
| stagflation-regime-24m | 30mo | regime |

Markdown drafts still live in `.claude/hypotheses/draft/` for future-edits-then-re-import; canonical copy is now the DB row.

## New architecture surface

### Modules added since last handoff
```
app/hypotheses/   — M-2: hypothesis object + invalidator DSL + nightly tick
app/views/        — M-2: markdown-with-frontmatter view registry parser
app/research/     — Phase 3: stress-test endpoint, Claude tool-use, vault-tick approval
app/core/schema_check.py — boot-time schema-drift WARN (replaces create_all)
tools/vault_indexer/ — Phase 2 sidecar (FastAPI on :8001, SQLite + sqlite-vec)
```

### New routes
```
/v1/hypotheses/*    M-2 CRUD + cancel
/v1/views/*         M-2 view registry
/v1/research/ask    Phase 3 stress-test (Claude tool-use)
/v1/research/queries[/...] Phase 3 history + approval webhook
```

### Frontend additions
```
/research                       Phase 3.7 single-turn UI
HypothesisStatusWidget          sidebar inset card; active + at_risk counts; hides at total=0
Sidebar Decisions group         gained "Research" entry with Sparkles icon
```

### Lifespan tasks (12 total now)
- Existing 10 (schedule-runner, accuracy-evaluator, drift-detector, daily-digest, market-data-derived, opportunities-tick, queue-worker, macro-ingestion, sync drain, outbox-purge)
- **+ hypothesis daily tick** (5-min initial deferral after boot)
- **+ research auto-stress** (weekly per active hypothesis)

### Migrations 0021–0023
- `0021_hypotheses` — `hypothesis` + `hypothesis_evaluation` tables
- `0022_hypothesis_node_links` — vault-indexer pointer table (TradingView ↔ vault nodes)
- `0023_research_queries` — Phase 3 audit table

## Decisions recorded

- ADR-013: hypothesis object — schema, DSL, cascade timing, ship-shape
- ADR-014: vault-indexer — substrate, storage, embedder, authoring discipline
- ADR-015: research stress-test endpoint — Phase 3

Index in [.claude/decisions/README.md](../decisions/README.md).

## Resolved this period (formerly open)

- **`create_all` racing alembic on boot** — happened twice in 24h (M-2 + Phase 2). Fix shipped in `d6b4cb6`: lifespan no longer calls `create_all`; `app/core/schema_check.warn_if_drift` runs at boot. Tests still build their schema from models in `tests/conftest.py` (only place create_all should run).
- **Drilldown blink-loop on bottom-row Accuracy buttons** — `onMouseLeave` / `onBlur` close handlers removed; closing is now explicit via × button. Hovering a different cell replaces drill state in place. See [.claude/accuracy.md](../modules/accuracy.md).
- **By Horizon mode** — new `?mode=anchor` (now the page default) treats picked date as the **made-on** day; per-cell target = anchor + horizon. Removes the "I have to backdate the picker to see actuals" friction. Legacy `?mode=target` retained.

## Open clarifying / parked

- **Auto-promote casual ticker to roster on N views?** Deferred — operator-driven adds healthier than usage-driven.
- **Sector holdings refresh cadence** — quarterly review noted in `frontend/src/lib/sector-holdings.ts` header.
- **Hypothesis re-evaluate every 12mo** — backlog item; first reviews due 2027-04-30 (mostly) and 2027-05-01 (stagflation). When 3.8 ships, the `next_review_at` field surfaces a banner on `/macro`.
- **Telegram bot setup** — Unlock #1 in backlog. Operator-driven 5-min setup, code already deploy-safe.

## Working environment

- **Backend:** `cd /Users/shourjosmac/Documents/Claude/TradingView && source venv/bin/activate && set -a && source .env.laptop && set +a && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. Postgres on `:5439` via `docker compose -f docker-compose.laptop.yml up -d`.
- **Vault-indexer:** see `.claude/vault.md` for the run command. Independent sidecar on `:8001`.
- **Frontend:** Vite preview MCP on `:3000`.
- **Tests:** `python -m pytest -q`. `tests/conftest.py` sets `DISABLE_LIFESPAN_BACKGROUND_TASKS=1` so fixtures tear down cleanly.

## Conventions / project memory

- **Caveman mode** — auto-active on session start.
- **Auto mode** — proceed without confirmation for low-risk work; stop and ask for destructive ops.
- **Neumorphic light theme is locked.** No dark mode, no glassmorphism.
- **Pre-execution checklist** before significant builds: git push current → DB snapshot via `docker exec ... pg_dump` → claude-mem MCP active.
- **Test gates between phases:** TS `tsc --noEmit` + `pytest -q` must be green before commit; one commit per phase.
- **Schema:** migration-driven only. **Do NOT add `Base.metadata.create_all` back to the lifespan.** That fix is load-bearing.
- **Documentation discipline:** every shipped feature gets module doc, plan doc flipped to SHIPPED, roadmap-shipped roll-up entry, CLAUDE.md cross-link if new module.

## Restart protocol

A fresh session should:
1. Read this file.
2. `git log --oneline e1b3f21..HEAD` for the 14-commit catch-up arc.
3. Check `.claude/backlog.md` for active deferred items (Telegram, hypothesis re-eval, etc.).
4. **If user wants to continue Phase 3.8** — read [`plans/phase-3.8-research-ui-threading.md`](../plans/phase-3.8-research-ui-threading.md) (direction notes; no full plan written yet).
5. **If user wants M-3** — wire hypotheses into Opportunities + Trades; ~1-2 days.
6. **If user wants Phase 3.1 (synthesis mode)** — `/research/digest` endpoint; ~4-6 hrs.
7. Caveman mode auto-active; auto-mode also active per session-start hooks.
