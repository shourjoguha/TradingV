# Roadmap — SHIPPED archive

> Phases 0-6 of the forecasting-tool → decision-support-tool transition. **All ✅ live as of 2026-04-27.** Kept for reference: each phase's spec, exit criteria, and post-ship retrospective.
>
> **Active roadmap** lives at [roadmap.md](roadmap.md). For the principles that drove the sequencing, see [principles.md](principles.md). For per-decision detail (e.g. "why Telegram over email"), see [decisions/](decisions/).

The shift: forecasting tool (Kronos predictions in, charts out, human decides) → decision-support tool (predictions → tested signals → tracked actions → measured outcomes). Each phase gated on the prior delivering real signal.

Reference brainstorm: chat session 2026-04-27.

## Retrospective notes (1 line per phase)

- **Phase 0** (snapshot): smooth. Tag + DB dump + bundle archive + ROLLBACK.md. Operator-driven Railway dump deferred (used Railway's built-in backup feature).
- **Phase 1.1** (accuracy backfill): smooth. 15 new tests covered math + integration; idempotency via `UNIQUE(prediction_id)` worked first try.
- **Phase 1.2** (`/accuracy` UI): smooth. Heatmap + drilldown built before live data — proved the "build-now-iterate-on-data" approach.
- **Phase 1.3** (drift + Telegram): backend complete; Telegram dormant pending operator bot setup ([backlog.md](backlog.md) Unlock #1).
- **Phase 2.1** (empty states): trivial as expected.
- **Phase 2.2** (lightweight-charts v5): **DEFERRED** — not on critical path; tracked separately.
- **Phase 3.1+3.2** (opportunities): smooth. Hardcoded rules + UNIQUE(prediction, rule) idempotency. Frontend tabs + cancel modal landed cleanly.
- **Phase 4** (Telegram digest): wired into Phase 1.3 commit. Daily loop ready; dormant pending setup.
- **Phase 5** (trades): smooth. P&L attribution by-rule will only be meaningful after several real trades.
- **Phase 6** (IV runway): yfinance ATM IV + earnings, daily refresh. Silently collecting.
- **Post-roadmap (queue + Neumorphism)**: shipped after Phase 6 — see [queue.md](queue.md), neumorphic redesign in [decisions/004](decisions/), [decisions/005](decisions/).
- **2026-04-30 — Accuracy + By Horizon visual update**: composite Accuracy metric (`hit% / MAPE%`) replaces hit-rate-only color so directionally-lucky-but-magnitude-wrong models stop reading green; added `1d | 1h | all` interval toggle (backend `interval` filter on `/v1/accuracy/grid`, no migration — field already on rows); low-n masking (`n < 4` greyed); click-drill replaced with hover/focus inline panel. By Horizon cells: `$` prefix removed from Δ% values, repeated "forecast" sub-text moved to legend, secondary reference now actual close (or italic predicted close for forecast-only cells), hover tooltip with side-by-side OHLC mini-candles. See [accuracy.md](accuracy.md) and [predictions.md](predictions.md) for cell semantics.
- **2026-04-30 — Self-healing OHLCV fetch**: accuracy evaluator's hourly tick now refreshes upstream OHLCV when a pending prediction's actual is missing; deduped per (ticker, interval) per tick, capped via new `ohlcv_fetch_misses` table after 24 attempts so unfetchable bars stop hammering yfinance. Sibling lazy-refresh added in `_process_task` warms caches for cold-start intervals (e.g. first 1h schedule). Resolves [backlog.md](backlog.md) Unlock #2. See [decisions/010](decisions/010-self-healing-ohlcv-fetch.md).
- **2026-04-30 — Scheduler mid-tick PUT race**: `record_run` now recomputes `next_run_at` against the freshly-loaded config (instead of a snapshot taken at tick start), so a `PUT /v1/schedule` landing during execution is honored on the way out — no more lost slots. No new flag, no new column. See [decisions/011](decisions/011-schedule-mid-tick-put-race.md).
- **2026-04-30 — Docs hub + jobs list redesign**: new `/docs` route (lazy-loaded). Markdown-driven reference docs with sticky scroll-spy TOC, segmented document switcher, persistent font-size control. v1 ships `metrics.md` (terms, formulas, color legends across the platform); `how-to-use.md` stubbed. Adding a doc = drop `.md` in `frontend/src/docs/` + register slug. `/analysis` page rebuilt: expandable rows replace the JobID-first table. New columns surface a friendly run summary (sym count · intervals · model), a stacked outcome bar (done/running/ineligible/error counts, lazy-fetched per row), smart relative timestamps (Today / Yesterday / MMM D), and duration. Per-task breakdown opens inline on row click — no round trip to the detail page for everyday triage. New deps: `react-markdown`, `remark-gfm`, `rehype-slug`. See [frontend/pages.md](frontend/pages.md).
- **2026-04-30 — Macro Workbench M-1 (signal layer)**: foundation for the regime-aware research workbench. New `macro_series` table (`migrations/0019`) holds daily close-only values from yfinance (~30 symbols) + FRED (~6 economic series). New module `app/macro/` with provider abstraction, hand-curated `registry.yaml`, service (`refresh`, `refresh_all`, `get_series`, `compute_ratio`), three `/v1/macro/*` endpoints, and a daily lifespan ingestion loop. Ratios are computed on demand (not materialised). Chunked-upsert (1000 rows/batch) avoids Postgres' 32767 bind-param limit on long-history symbols. 16 new tests (idempotency, value updates, ratio inner-join, zero-denom skip, registry fan-out, error isolation, route round-trips, FRED CSV parser, chunked-upsert regression). First live tick: 38/38 symbols ok, 220k rows. See [macro.md](macro.md), [decisions/012](decisions/012-macro-workbench-storage-shape.md), [plans/M-1-signal-layer.md](plans/M-1-signal-layer.md).

## North-star principles

1. **Trust before action.** Every "tradeable" claim must be backed by visible accuracy data sliced by `(ticker, horizon, model)`. Aggregate stats lie.
2. **Cheap reversibility.** Every phase tagged in git; rollback path documented in `backups/ROLLBACK.md`.
3. **Single-user, opinionated UX.** No auth tiers, no permissions. The cost of premature generality is higher than the cost of refactoring later.
4. **External channels stay external.** This app is the *quantitative pillar*; news, policy, expert commentary, manual TV chart reads stay out of scope. Plug in only data the model itself emits or that's required to evaluate it.

## Locked decisions (2026-04-27)

| Decision | Choice |
|---|---|
| Accuracy metrics | MAPE, RMSE, directional hit-rate (all three, computed per `(ticker, horizon, model)`) |
| Backfill scope | Existing prediction history only — no special historical batch job |
| Drift threshold | Recent-30d MAPE > 1.5× all-time MAPE for that pair triggers flag (start strict, tune after 1 week of data) |
| Notification channel | Telegram bot (single channel for v1; email deferred) |
| Sequencing | Snapshot → Trust → UX → Actionability → Push → Journal → Options runway |

---

## Phase 0 — Snapshot (rollback safety) · ~30 min

Capture the current cloud-deployed v1 (CF Pages frontend at `tradingv-83b.pages.dev` + Railway backend) in case Phase 1+ goes sideways.

Artifacts (in `backups/` — gitignored except docs):
1. **Git tag** `v1.0-pre-trust-sprint` annotated at current main HEAD.
2. **Laptop Postgres dump** via `pg_dump` of `.env.laptop`'s `DATABASE_URL`.
3. **Railway Postgres dump** — operator-driven (Railway CLI or psql via Railway DATABASE_URL).
4. **OpenAPI JSON snapshot** from Railway (`/openapi.json`) — captures API contract.
5. **Frontend bundle archive** — copy `frontend/dist/` to `backups/frontend-dist-YYYY-MM-DD/`.
6. **Env-var inventory** — operator-driven copy of Railway + CF Pages env vars to `backups/env-inventory-YYYY-MM-DD.md` (gitignored, contains keys).

Rollback path: `backups/ROLLBACK.md` (committed) names exact commands to revert: git checkout the tag, restore SQL dumps, rollback CF deployment to specific hash, re-set env vars.

**Note**: Laptop DB and Railway DB are bidirectionally synced via Tailscale (Phase B1+B2). A laptop dump is functionally a Railway dump modulo unsynced rows in flight. Both are still captured for paranoia.

---

## Phase 1 — Trust through feedback · ~1.5 weeks · PRIORITY

**One mandate**: prove or disprove Kronos accuracy at every `(ticker, horizon, model)` pair you might trade.

### 1.1 — Accuracy backfill + persistence (~3 days)

New table `prediction_accuracy`:
```sql
prediction_accuracy(
  id, prediction_id FK, ticker, horizon_bars, model_id,
  predicted_close NUMERIC, actual_close NUMERIC,
  error_pct NUMERIC,           -- (actual - predicted) / actual
  error_abs NUMERIC,           -- |actual - predicted|
  direction_correct BOOL,      -- sign(predicted_change) == sign(actual_change)
  generated_at TIMESTAMPTZ,
  evaluated_at TIMESTAMPTZ,
  UNIQUE(prediction_id)        -- idempotency
)
```

Background job `accuracy_evaluator()` ticks daily after market close: pulls all `prediction_points` whose horizon has elapsed and aren't yet in `prediction_accuracy`, fetches `actual_close` via existing OHLCV provider, computes errors, inserts row. Idempotent.

Backfill: run once on existing `prediction_points` history (~5 jobs of data). No special historical batch.

### 1.2 — Per-(ticker, horizon) accuracy dashboard (~3 days)

New page `/accuracy`:
- **Heatmap table**: rows = watchlist tickers, columns = horizons in scheduled run (1d, 3d, 5d, 10d). Cells = directional hit-rate over last 30 evaluated predictions (color-graded: green ≥ 60%, yellow 50-60%, red < 50%). Secondary metric (MAPE %) shown on cell hover.
- **Drilldown** on cell click: scatter plot predicted vs actual (diagonal = perfect), MAPE/RMSE/hit-rate trio, sparkline of accuracy over time, list of recent prediction ↔ actual pairs.
- **Filters**: date range, model_id (when ensemble lands).

### 1.3 — Drift detection + Telegram alerts (~3 days)

Daily cron compares last-30d MAPE to all-time MAPE per `(ticker, horizon, model)`. Flag if recent > 1.5× all-time AND ≥ 10 evaluations in recent window (avoid noise on sparse data).

New table `drift_alerts(id, ticker, horizon, model_id, recent_mape, allTime_mape, ratio, flagged_at, acknowledged_at)`.

Telegram integration:
- Bot setup via @BotFather (one-time, manual).
- New env var `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (your DM with the bot).
- New `app/notifications/telegram.py` posts markdown messages.
- Drift alerts → Telegram immediately. Daily morning digest (Phase 4) reuses same channel.

Drift alerts also surface as a banner on `/accuracy` and `/` (dashboard) until acknowledged.

### Phase 1 exit criteria (gates Phase 3)

- ≥ 1 `(ticker, horizon)` pair with directional hit-rate ≥ 60% over ≥ 20 evaluations.
- Accuracy dashboard renders without empty states for all watchlist tickers.
- Telegram drift alert verified end-to-end (force a drift via test data).

If exit fails → pivot to retraining / model-side investigation, not Phase 3.

---

## Phase 2 — UX hardening · ~3 days · parallel-able with Phase 1

### 2.1 — Empty states pass

By-target, by-horizon, analysis pages currently render blank when there's no data. Replace with a meaningful "No data yet" UI per page, with a single CTA pointing at the first-action ("Run your first analysis" → opens Run dialog).

### 2.2 — lightweight-charts v4 → v5 upgrade

v5 brings: crosshair sync between panes, drawing tools, multi-pane (sets up prediction-vs-actual overlay for Phase 1.2), better mobile touch. Breaking changes minor; check release notes.

Bonus: add prediction-vs-actual line overlay on `/predictions/by-target` chart — doubles as a Phase 1 visualization.

(Plotly explicitly NOT chosen here — see backlog entry "Charting library — lightweight-charts v5 chosen over Plotly".)

---

## Phase 3 — Actionability bridge (signals layer) · ~2 weeks

**Predicate**: Phase 1 exit criteria met.

### 3.1 — Opportunities table + signal generator

```sql
opportunities(
  id, ticker, kind ENUM('buy','sell'), generated_at,
  source_prediction_id FK, source_model_id,
  rule_id, rule_label,
  predicted_move_pct NUMERIC, confidence NUMERIC,
  status ENUM('open','acted','expired','dismissed'),
  expires_at,
  acted_at, dismissed_at, dismissed_reason
)
```

Hardcoded rules to start (NOT a DSL):
- `R1`: predicted_move_pct ≥ +2% over 5d AND historical_hit_rate ≥ 0.60 → BUY.
- `R2`: predicted_move_pct ≤ -2% over 5d AND historical_hit_rate ≥ 0.60 → SELL.
- `R3`: predicted_move_pct ≥ +5% over 10d AND historical_hit_rate ≥ 0.55 → BUY.
- (Tune after 2 weeks of real signal data.)

Generator runs after each scheduled prediction batch.

### 3.2 — Opportunities UI

New page `/opportunities`:
- Today's open list (sorted by confidence × predicted_move).
- History tab (acted + dismissed + expired with realized outcomes).
- Per-row actions: mark acted, dismiss (with reason).

---

## Phase 4 — Daily Telegram digest · ~2 days

Predicate: Phase 3 generates ≥ 1 opportunity per typical day.

Cron at 8 AM operator-tz posts to Telegram:
- Top N open opportunities (markdown table).
- Any unacknowledged drift alerts.
- One-line summary of last night's run.

Reuses Telegram infra from Phase 1.3.

---

## Phase 5 — Trade journal · ~1 week

Predicate: 2 weeks of opportunities feed observed; user has acted on ≥ a few.

```sql
trades(
  id, opportunity_id FK NULLABLE, ticker, side ENUM('buy','sell'),
  qty INT, entry_price NUMERIC, entry_at TIMESTAMPTZ,
  exit_price NUMERIC, exit_at TIMESTAMPTZ,
  realized_pnl NUMERIC, fees NUMERIC, notes_md TEXT
)
```

Manual entry. Brokerage-API integration explicitly out of scope (single user, friction not worth it). One-click "create trade from opportunity" button on opportunities page prefills fields.

`/trades` page: list view + entry form + simple P&L summary (today / week / month / all-time).

Per-opportunity P&L attribution: "If you'd taken every BUY opportunity Kronos surfaced from rule R1, your P&L would be X." Closes the feedback loop on whether Kronos is worth trading on.

---

## Phase 6 — Options runway data layer · ~2 days · tucks into Phase 3 sprint

Single background job: pull IV percentile + earnings date for each watchlist ticker (free source: yfinance, polygon free tier, or similar). Two new columns on `tickers` (or new `ticker_market_data` table — TBD). No UI yet. Just data accumulating.

Sets up the eventual options chapter (strategy generator, IV surfaces) without blocking Phase 1-5.

---

## Out of scope (explicit)

- News/policy/commentary ingestion (user owns these channels manually)
- Brokerage API integration (single user, manual entry friction acceptable)
- Multi-user / auth tiers / sharing
- Mobile-first responsive layout (Telegram serves mobile; desktop-first web is fine)
- Backtesting infrastructure beyond what `prediction_accuracy` provides
- Multi-model ensemble (defer until at least one second model exists)
- Public tunnel for laptop (separate backlog)

---

## Estimated total

~5 weeks of focused work to "decision-support tool", gated phase-by-phase. Stop early at any phase whose exit criteria don't hit — that's the signal that Kronos isn't ready for the next layer of investment.
