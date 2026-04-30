# Session handoff — 2026-05-01

> **Next-session quick-start:** read this file, then `git log --oneline 191aa6c..HEAD` for recent shipped work. Active plans linked at the bottom. State below is good as of HEAD = `21dda1d`.

## Where things stand

- **Tree clean, pushed to origin/main.** Last commit `21dda1d` (multi-watchlist sector drill-in).
- **Backend tests:** 289/289 green.
- **TypeScript:** `tsc --noEmit` clean.
- **Live laptop backend** running on `:8000`; frontend dev on `:3000`.
- **Postgres** at migration head `0020_boards_and_quotes`. Live DB columns added for `ticker_market_data` quote fields via direct `ALTER` (lifespan `create_all` doesn't add columns to existing tables — note this gotcha for future migrations).

## What just shipped (last ~10 commits)

| # | Commit | Subject |
|---|---|---|
| 1 | `21dda1d` | MW-3: sector top-10 drill-in + `/v1/quotes` bulk endpoint |
| 2 | `9221abf` | MW-2: boards (UI: Watchlists) + quote columns + daily cron extension |
| 3 | `c35f2c6` | MW-1: UI rebrand `/watchlist` → `/roster` |
| 4 | `522bbd6` | Row InfoBubble tooltip fix + directional context on every ratio |
| 5 | `5ebdcea` | Stagflation regime panel + spread endpoint + 6 new ratios |
| 6 | `2a77b6b` | UI consolidation Phase E (mobile horizontal scroll) |
| 7 | `8106dc3` | UI consolidation Phase D (HoverTooltip + InfoBubble + glossary) |
| 8 | `2cfdaea` | UI consolidation Phase C (PageHeader / EmptyState / LoadingStates) |
| 9 | `67e4bf1` | UI consolidation Phase B (Dashboard rebuild) |
| 10 | `6fc7dbc` | UI consolidation Phase A (sidebar IA + redirects) |

## Active phases / open plans

| Plan | Status | Path |
|---|---|---|
| **M-2 Hypothesis object + view registry** | Outline only; ready to plan | [.claude/plans/M-2-hypothesis-object.md](plans/M-2-hypothesis-object.md) |
| M-3..M-6 Macro Workbench | Candidates in roadmap | [.claude/roadmap.md](roadmap.md) |
| 12-month hypothesis re-evaluation | Backlog item; first reviews due 2027-04-30 | [.claude/backlog.md](backlog.md) |

**Strongest next-move signal from the operator:** M-2 was deferred deliberately ("we'll pick up M-2 later and go over remaining open questions as well"). Whenever the operator says "go M-2," convert the outline into a full plan + execute.

## Hypotheses on disk (6 drafts)

[.claude/hypotheses/draft/](hypotheses/draft/) — not yet ingested into a DB (M-2 ships that).

| Slug | TTL | Type |
|---|---|---|
| latam-breakout-36m | 36mo | parent (structural) |
| latam-breakout-18m | 18mo | child of 36m (tactical) |
| saas-mission-critical-2x-18m | 18mo | OKTA + PATH 2x basket |
| btc-bottom-3m | 3mo | precondition |
| btc-rally-24m | 24mo | dependent on bottom-3m |
| stagflation-regime-24m | 24mo | regime_shift |

Schema sketched in [.claude/macro-workbench-brainstorm.md](macro-workbench-brainstorm.md). M-2 implements: `slug`, `parent_id`, `precondition_id`, `claim_type`, `primary_metric`, `tracking_signal`, lifecycle status (`active|confirming|violated|stale|cancelled`), TTL auto-deprecate, manual cancel.

## Architecture state

### Modules in app/
```
core, alerts, tickers, market_data, kronos, analysis, sync,
watchlist (operational; UI: "Roster"), schedule, predictions,
accuracy, opportunities, trades, notifications, labels,
macro, boards (casual; UI: "Watchlists"), api, queue
```

### Lifespan tasks (10 total)
```
schedule-runner, accuracy-evaluator, drift-detector, daily-digest,
market-data-derived, opportunities-tick, queue-worker,
macro-ingestion, sync drain (continuous), outbox-purge (hourly)
```

### Frontend routes (14)
```
/                          Dashboard (regime strip + tiles)
/macro/:tab?               Decisions → Macro (lazy; 5 panels + ratios + sectors)
/predictions/:tab?         Decisions → Predictions (horizon | target | accuracy)
/motion/:tab?              Decisions → Motion (opportunities | trades)
/watchlists/:boardId?      Decisions → Watchlists (casual lists, lazy)
/roster                    Admin → Roster (operational, drives Kronos)
/schedule                  Admin → Schedule
/health, /health/:jobId    Admin → Health (was /analysis)
/docs/:slug?               Docs (lazy; metrics + how-to-use)
/tickers/:symbol/labels    EAV labels page
/                          Plus legacy redirects (every old URL)
```

### DB migrations
- Head `0020`. Most recent additions: `boards`, `board_tickers`, `ohlcv_fetch_misses` (0018), `macro_series` (0019), `boards + quotes` (0020).
- Live laptop schema already at head; remember the `lifespan create_all only creates tables, not new columns` gotcha — direct `ALTER` for column adds.

## Working environment

- **Backend:** `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` with `.env.laptop` sourced. Postgres on `:5439` via `docker compose -f docker-compose.laptop.yml up -d`.
- **Frontend:** `pnpm dev`-equivalent via the preview MCP on `:3000`.
- **API_KEY** in `.env.laptop`. Permission-blocked from Bash `cat .env*` — don't try to read it.

## Conventions / project memory

- **Caveman mode** has been active throughout this session for terse responses. Toggle with `stop caveman` / `normal mode`.
- **Auto mode** active — proceed without confirmation for low-risk work; stop and ask for destructive ops.
- **Neumorphic light theme is locked.** No dark mode, no glassmorphism. Operator preference.
- **Pre-execution checklist** before significant builds: git push current → DB snapshot via `docker exec ... pg_dump` → claude-mem MCP active.
- **Test gates between phases:** TS `tsc --noEmit` + `pytest -q` must be green before commit; one commit per phase.
- **Documentation discipline:** every shipped feature gets:
  - Module doc in `.claude/<module>.md`
  - Plan doc in `.claude/plans/<phase>.md` flipped to SHIPPED
  - Roll-up entry in `.claude/roadmap-shipped.md`
  - Cross-link in `CLAUDE.md` module table when it adds a new module

## Skills installed (relevant)

- `ui-ux-pro-max` — at `~/.claude/skills/ui-ux-pro-max`. Run via `python3 src/ui-ux-pro-max/scripts/search.py "<query>" --domain <product|style|chart|ux>`.
- `frontend-design` — at `~/.claude/skills/frontend-design`.
- `claude-mem` MCP — search via `mcp__plugin_claude-mem_mcp-search__search`.
- Caveman mode skills.

## Open clarifying questions / parking lot

- **Auto-promote casual ticker to roster on N views?** Deferred — operator-driven adds healthier than usage-driven.
- **Sector holdings refresh cadence** — currently hardcoded; quarterly review noted in `frontend/src/lib/sector-holdings.ts` header.
- **TTL defaults per regime axis** — long-horizon 24-36mo, tactical 3-6mo. Lock when M-2 plan is written.
- **Invalidator language for hypotheses** — small enumerated set proposed in [.claude/plans/M-2-hypothesis-object.md](plans/M-2-hypothesis-object.md). Confirm + implement when M-2 is active.

## Restart protocol

A fresh session should:
1. Read this file first.
2. `git log --oneline 191aa6c..HEAD` for full session-arc context.
3. Check `.claude/backlog.md` for open items (Telegram setup, hypothesis re-eval, etc.).
4. If user says "go M-2" / "continue M-2" — convert [.claude/plans/M-2-hypothesis-object.md](plans/M-2-hypothesis-object.md) outline into a full plan, then execute.
5. Caveman mode auto-active per session-start hook.
6. Use claude-mem search if a specific decision rationale needs recall — most rationale is already in `.claude/decisions/<NNN>-*.md` ADRs (12 ADRs as of HEAD).
