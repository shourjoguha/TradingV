# Plan — rx finance panel v1.x.1 (TradingV side)

Built from brief in `~/.claude/commands/rx-finance.md` (loaded 2026-05-16). TradingV becomes exclusive surface for finance recommendations per D-045 (storage-routing lock). Lovable handles fitness+nutrition only.

## Brief vs reality reconciliation

| Brief assumption | Reality | Resolution |
|---|---|---|
| `migrations/NNNN_create_recommendations.sql` | Alembic-driven (`migrations/versions/*.py`). Last rev: `0028_ticker_review_queue` | Create alembic rev `0029_recommendations.py` |
| `CREATE TABLE trades (...)` w/ `qty,price,executed_at,related_rec_id,side ∈ {long,short,close_long,close_short}` | `trades` already exists w/ `opportunity_id, entry_price/exit_price, entry_at/exit_at, side ∈ {buy,sell}, realized_pnl, fees, context_refs[]` | DO NOT recreate. ADD `related_rec_id` FK column + index in same rev `0029`. Reuse existing entry/exit semantics; brief's "trade capture form" maps `qty→qty, price→entry_price, executed_at→entry_at` |
| TradingV "panel" at `/rx/finance` | React SPA under `frontend/`; backend serves `/v1/*` JSON only | Backend: `/v1/rx/*` JSON endpoints. Frontend: new pages `pages/rx-finance-recs.tsx` + `pages/rx-finance-rec-detail.tsx` + extend existing `trades`/`hypotheses` pages w/ rec linkage |
| `owner_user_id UUID NOT NULL` single hardcoded operator | TradingV is single-user; no existing owner scoping | Include column for Supabase schema parity but server-side-set from `SETTINGS.RX_OPERATOR_UUID` env var (default: `9312c7a0-d09c-4663-8f67-5dfddfdb6249`). Never trust client. |
| `1kb_Shos` `tradingview` source = read-only | Confirmed | Use FastAPI `POST /v1/rx/recs` w/ shared-secret auth (Option A in brief) |
| Phase W reconciler split | Lives in `/rx-finance` slash command on laptop, not TradingV | Out of TradingV scope. Coordinate via SESSION-HANDOFF when ingestion endpoint stabilizes |

## Phasing (council recommendation: split a/b)

### Phase v1.x.1-a — Rec consumption (Part A in brief)

Goal: operator can read+disposition finance recs in TradingV. `/rx-finance` slash command can dual-write here.

**Files created:**
- `migrations/versions/0029_recommendations.py` — `recommendations` table + add `trades.related_rec_id` FK col
- `app/rx/__init__.py`
- `app/rx/models.py` — `Recommendation` ORM model (mirrors brief schema, CHECK domain='finance' via Postgres-only constraint)
- `app/rx/schemas.py` — Pydantic: `RecCreate`, `RecRead`, `RecListItem`, `DispositionWrite`, `SnoozeWrite`
- `app/rx/service.py` — list/get/create/disposition/snooze; defensive `domain='finance'` filter on every read
- `app/rx/routes.py` — `POST /v1/rx/recs` (ingest, X-RX-Ingest-Token auth), `GET /v1/rx/recs`, `GET /v1/rx/recs/{id}`, `POST /v1/rx/recs/{id}/disposition`, `POST /v1/rx/recs/{id}/snooze`
- `app/core/auth.py` — add `verify_rx_ingest_token` dep (env: `RX_INGEST_TOKEN`)
- `frontend/src/pages/rx-finance-recs.tsx` — list view
- `frontend/src/pages/rx-finance-rec-detail.tsx` — detail + disposition UI
- `frontend/src/hooks/use-rx-recs.ts` — `useRxRecs()`, `useRxRec(id)`, `useDispositionRec`, `useSnoozeRec` mutations
- `frontend/src/lib/api.ts` — extend w/ `rxRecs.*` namespace
- `tests/test_rx_routes.py` — ingest auth, list filter, disposition writes, snooze count increments, CHECK constraint rejection
- `tests/test_rx_service.py` — service-layer unit tests

**Files edited:**
- `app/api/router.py` — mount `rx_router` under `/v1`
- `app/main.py` — `from app.rx import models as _rx_models  # noqa: F401`
- `app/core/config.py` — add `RX_OPERATOR_UUID`, `RX_INGEST_TOKEN` settings
- `frontend/src/App.tsx` (or route registry) — register `/rx-finance` + `/rx-finance/:id`
- `.claude/modules/` — new `rx.md` module doc
- `.claude/status/roadmap-shipped.md` — log v1.x.1-a retro

**Verification (must all pass before -b):**
1. `alembic upgrade head` clean against local pg
2. `pytest tests/test_rx_routes.py tests/test_rx_service.py` green
3. CHECK constraint rejects `INSERT (domain='fitness')` row
4. `POST /v1/rx/recs` without `X-RX-Ingest-Token` → 401
5. `POST /v1/rx/recs` with valid token + payload → 201 + row visible via `GET /v1/rx/recs`
6. List endpoint default 60-day window + ordering matches SQL in brief
7. Disposition write: `status=acted`, `acted_disposition`, `acted_at`, `subjective_fit_1_5`, `outcome_note` all persist
8. Snooze write: `snoozed_until = NOW() + N days`, `snooze_count++`, warns at >=2 (frontend toast)
9. Detail page renders `body_md` as markdown + expandable JSON block for breakdowns
10. Forced-decision red banner shows when `snooze_count >= 2`
11. Aging red dot when `age_days > 14`
12. Auto-revive: rows where `snoozed_until < NOW()` render as "open (auto-revived)" in list

### Phase v1.x.1-b — TradingV-native value (Part B in brief)

Goal: link recs ↔ hypotheses ↔ trades; close Phase I unlock for `position_thesis_match`.

**Files edited (no new modules — extend existing):**
- `app/hypotheses/routes.py` — new `GET /v1/hypotheses/health` returning ticker/thesis_short/status/age_days/days_to_expiry/`related_recs_count` (heuristic: `body_md ILIKE '%' || ticker || '%'`)
- `app/hypotheses/service.py` — health aggregation w/ rec count subquery
- `app/trades/models.py` — column already added in `0029` migration; nothing to change in ORM if we add it there
- `app/trades/routes.py` — extend trade-create payload w/ optional `related_rec_id`; new `GET /v1/trades/positions` returning per-ticker aggregation (qty, avg_price, current_value, %portfolio) + risk flags from `Lakshmi/01_rules/risk_rules.md`
- `app/trades/service.py` — position aggregation + risk-flag computation (>5% single, >50% sector). Sector lookup: fallback ticker when no sector data.
- `app/rx/routes.py` — `GET /v1/rx/recs/{id}/links` returning `{hypotheses: [...], trades: [...]}` (ticker substring match in `body_md`)
- `app/rx/service.py` — link resolution helper
- `frontend/src/pages/rx-finance-rec-detail.tsx` — add Hypotheses + Trades inline lists from `/links`
- `frontend/src/pages/rx-finance-hypotheses.tsx` (NEW) — hypothesis health table
- `frontend/src/pages/rx-finance-positions.tsx` (NEW) — position-exposure view
- `frontend/src/pages/trades-new.tsx` (or extend existing trade form) — add `related_rec_id` autocomplete dropdown (filters: domain='finance', created_at > NOW - 30d)
- `frontend/src/hooks/use-positions.ts` (NEW)
- `frontend/src/hooks/use-hypothesis-health.ts` (NEW)
- `tests/test_rx_links.py` — link heuristic, FK integrity
- `tests/test_positions.py` — aggregation math, risk flags
- `tests/test_hypothesis_health.py` — counts + age math

**Verification:**
1. Hypothesis health endpoint <500ms on full dataset
2. Position aggregation matches `SUM(qty*price)` on synthetic data
3. Risk flags fire for synthetic >5% single + >50% sector
4. Trade form persists w/ `related_rec_id` FK (verified by SELECT join)
5. Autocomplete returns ≤30d finance recs only
6. Rec detail page lists linked hypotheses + trades; click-through navigates correctly

### Phase I unlock (after both -a + -b)

7. Coordinate w/ rx-layer agent (laptop): update `~/.claude/commands/rx-finance.md` step 9.5 — switch rec-write target from Supabase to `POST http://localhost:8000/v1/rx/recs` w/ `X-RX-Ingest-Token`
8. After 1 real trade w/ `related_rec_id` populated: `position_thesis_match` signal in `/rx-finance` reads real position data from TradingV `trades` aggregate (currently stub)
9. Log D-046 in `~/Documents/Sho's Playgroun/rx-meta/DECISIONS-LOG.md`: ingestion path chosen, Phase I cutover timestamp, deviations

## Hard boundaries

- ❌ NO Supabase reads/writes from TradingV
- ❌ NO `domain != 'finance'` rows (CHECK constraint + defensive WHERE)
- ❌ NO rec generation from TradingV (Claude Code `/rx-finance` only — D-030)
- ❌ NO Lovable code or Supabase migration touches
- ❌ NEVER log `X-RX-Ingest-Token` (env var, redact in debug)

## Open questions deferred (operator-redirectable mid-flight)

- Markdown renderer choice for frontend: `react-markdown` likely already in deps — verify in package.json before adding
- Sector lookup data source: TradingV has no sector table. Fallback = group by ticker only; flag the gap in v1.x.1-b retro for future sector-enrichment phase
- `current_value` in positions: needs live quote. Use `app/market_data` latest OHLCV close as proxy (no live yfinance hit on every page load — too slow)

## Time estimate

- v1.x.1-a: ~3-4 hours (migration + module scaffold + 2 React pages + tests)
- v1.x.1-b: ~3-4 hours (3 new pages + position aggregation + link heuristic + tests)
- Phase I cutover coordination: 30 min (handoff doc + rx-layer command edit)

## Resume protocol

If session ends mid-phase: write `.claude/sessions/SESSION-HANDOFF.md` w/ current phase + last completed file + next file. Operator resumes: *"Read TradingView/.claude/sessions/SESSION-HANDOFF.md and continue rx finance panel."*
