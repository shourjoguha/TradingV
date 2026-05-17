# rx — prescription layer (finance only)

## What it is

TradingV is the **exclusive surface for finance recommendations** per D-045 (storage-routing lock). Lovable/Supabase handles fitness + nutrition; finance lives here in the local Postgres. Generation lives on the laptop (`/rx-finance` slash command in `~/.claude/commands/`); TradingV ingests, renders, and disposition.

## Schema

`recommendations` table (alembic rev `0029`):
- `id` UUID-string PK
- `owner_user_id` server-stamped from `RX_OPERATOR_UUID` env, **never** trusted from client payload
- `domain` CHECK constraint enforces `= 'finance'` (defense-in-depth above defensive `WHERE` filter in every service read)
- `status` CHECK enforces `IN ('open','snoozed','acted','dismissed')`
- `subjective_fit_1_5` CHECK enforces `BETWEEN 1 AND 5`
- `drift_score`, `confidence`, `tldr`, `body_md`, `rx_md_path`
- `facts_json`, `source_refs`, `signals_fired`, `drift_breakdown`, `confidence_breakdown` — opaque JSON
- `acted_disposition`, `acted_at`, `subjective_fit_1_5`, `outcome_note` — disposition trail
- `snoozed_until`, `snooze_count` — snooze trail
- Indexes: `(status, created_at DESC)`, `(snoozed_until)` partial WHERE NOT NULL, `(owner_user_id)`

`trades.related_rec_id` — nullable FK to `recommendations(id)` ON DELETE SET NULL. Trades survive rec deletion. Powers the `position_thesis_match` signal in `/rx-finance` once Phase B trade-capture form lands.

## Endpoints

All under `/v1/rx/` unless noted:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/v1/rx/recs` | `X-RX-Ingest-Token` | Ingest from laptop's `/rx-finance` |
| GET | `/v1/rx/recs` | `X-API-Key` | List w/ rolling window (default 60d, max 200) |
| GET | `/v1/rx/recs/{id}` | `X-API-Key` | Full detail |
| POST | `/v1/rx/recs/{id}/disposition` | `X-API-Key` | Operator disposition (acted_*/skipped/dismissed) |
| POST | `/v1/rx/recs/{id}/snooze` | `X-API-Key` | Snooze N days (1-7) |
| GET | `/v1/rx/recs/{id}/links` | `X-API-Key` | Hypothesis + trade cross-references (v1.x.1-b) |
| GET | `/v1/hypotheses/health/list` | `X-API-Key` | Hypothesis health view w/ related rec counts (v1.x.1-b) |
| GET | `/v1/trades/positions` | `X-API-Key` | Open position aggregation w/ risk flags (v1.x.1-b) |

**Auth split rationale:** ingest token can be rotated independently and a compromised ingest token can't read or disposition existing recs. Empty `RX_INGEST_TOKEN` env → 503 on ingest (fail-loud) instead of silently accepting unauthenticated writes.

## Service-layer guards (above DB CHECK)

1. **Domain validation**: Pydantic `Literal["finance"]` + service-level `ValueError` + DB CHECK
2. **Owner UUID**: server-stamped from `SETTINGS.RX_OPERATOR_UUID`; client-supplied `owner_user_id` in payload silently ignored (Pydantic schema does not declare it)
3. **Terminal-state guard**: `disposition()` and `snooze()` reject writes when `status IN ('acted','dismissed')` to preserve audit trail
4. **TZ coercion**: `created_at` overrides from payload pass through `_ensure_aware` to avoid aware-vs-naive comparison bugs on Postgres
5. **subjective_fit required**: `acted_as_prescribed`/`acted_modified` dispositions require `subjective_fit_1_5` (1-5); skipped/dismissed don't

## Derived fields on list/detail reads

Server-computed; one source of truth:
- `forced_decision` — `snooze_count >= 2` (threshold `_FORCED_DECISION_SNOOZE_COUNT` in `service.py`)
- `aging` — `age_days > 14`
- `auto_revived` — `status='snoozed' AND snoozed_until < NOW()`
- `short_id` — first 8 chars of UUID for compact display

## Frontend (IA-integrated 2026-05-16)

rx-finance does NOT have its own sidebar entry. The four sub-surfaces are folded into the existing IA along the operator's natural job boundary:

| Surface | Route | Lives inside |
|---|---|---|
| Rec list | `/motion/recs` | Motion tab (Signals group) |
| Rec detail | `/motion/recs/:id` | Motion shell short-circuit |
| Position exposure | `/motion/positions` | Motion tab |
| Hypothesis health | `/theses/health` | Theses tab |
| Open-rec morning glance | `<RxStrip />` on `/` | Today strip (top-3 ranked by forced > aging > drift_score) |

Page modules (lazy-loaded via Motion/ThesesShell):
- `pages/Motion.tsx` — tabs `Opportunities | Trades | Positions | Recommendations` + detail short-circuit
- `pages/ThesesShell.tsx` — tabs `List | Health` wrapping the existing Theses page
- `pages/RxFinance.tsx`, `pages/RxFinanceDetail.tsx`, `pages/RxFinancePositions.tsx`, `pages/RxFinanceHypotheses.tsx` — content components (no longer top-level routes)
- `components/today/RxStrip.tsx` — Today landing strip; hidden when no open recs

Legacy `/rx-finance*` routes redirect into the new locations (preserves any operator bookmarks).

`Trades.tsx` form extended w/ optional `related_rec_id` autocomplete (filters to finance recs from last 30d).

Hooks in `hooks/use-api.ts`:
- `useRxRecs({ window_days, limit })`, `useRxRec(id)`
- `useDispositionRec()`, `useSnoozeRec()` — both invalidate list + detail queries; success toast cites Lakshmi reconcile on next `/rx-finance` run

## Workflow

```
laptop                                  TradingV                       Lakshmi markdown
  /rx-finance generates rec            POST /v1/rx/recs
                                         → row inserted (status=open)
                                       ← 201 { id }
                                       UI: operator opens /rx-finance
                                            disposition click
                                       POST /v1/rx/recs/{id}/disposition
                                         → status='acted', acted_at, fit
  next /rx-finance run                   ← 200
    step 0.7 reads recommendations
    reconciles frontmatter -------------------------> rx-fin-*.md updated
```

## Hard rules

- ❌ NO Supabase reads/writes from TradingV
- ❌ NO `domain != 'finance'` rows accepted (3 layers: Pydantic Literal, service ValueError, DB CHECK)
- ❌ NEVER log `RX_INGEST_TOKEN` — boot log reports configured/unset state only
- ❌ NO rec generation from TradingV (only laptop `/rx-finance`)
- ❌ NO Lovable code or Supabase migration touches

## v1.x.1-b heuristics + known limitations

- **Hypothesis-rec linkage** (`/v1/hypotheses/health/list` + `/v1/rx/recs/{id}/links`): case-insensitive substring of hypothesis title in rec `tldr|body_md`. Min title length 3 to avoid noise. False-positive prone on common substrings; future = explicit FK on rec → hypothesis.
- **Ticker-trade linkage** (`/v1/rx/recs/{id}/links`): regex `\b[A-Z]{2,5}\b` matches ticker candidates; `_TICKER_NOISE_DENYLIST` strips common non-ticker tokens (USA, GDP, FED, BUY, CEO, IPO, etc.). Trade match is bounded to open positions OR closed within last 90d to avoid stale matches.
- **Position aggregation** (`/v1/trades/positions`): single grouped OHLCV query (no N+1 round-trips). Daily-bar preferred; any-interval fallback. Trade rows materialized to dicts before session close to avoid lazy-load on detached instances.
- **Risk thresholds**: `>5% single position` enforced; source-of-truth = `Sho's Playgroun/Lakshmi/01_rules/risk_rules.md` (operator vault, not in repo). Constants `RISK_SINGLE_POSITION_THRESHOLD`, `RISK_SECTOR_THRESHOLD` in `app/trades/service.py` mirror the file.
- **Sector concentration**: NOT computed — TradingV has no sector lookup table. Risk-flag-sector always False; gap for v1.x.1-c.
- **`current_price` source**: latest `ohlcv_bars.close` for ticker. Falls back to entry-price when no quote cached (e.g. a brand-new ticker before daily OHLCV runs).

## Operator-attention axis (2026-05-17 — Phase 2 of tv-context-decision-engine-enrichment)

Closes the second of 3 TV-context decision-engine gaps. New columns on
`recommendations`:

- `attention_score FLOAT NULL` — weighted-decayed sum across kinds.
- `attention_breakdown JSON NULL` — `{ticker: {kind: count, score: float}}`.

Computed at rec creation by `app/rx/tv_context_signal.py:compute_attention_for_rec`:

1. Pulls tickers from `tldr + body_md` via the same `_TICKER_TOKEN_RE` +
   `_TICKER_NOISE_DENYLIST` already used by `links_for_rec`.
2. For each ticker, queries `tv_context_items` in trailing 14 days.
3. Per-item: `weight = DEFAULT_KIND_WEIGHTS[kind]` × `exp(-ln2 × age_d / 7)`.
4. Top-level `score = MAX` across tickers (NOT sum — a rec touching a
   heavily-discussed name shouldn't be diluted by sibling tickers).

**Locked tuning:**

```python
DEFAULT_KIND_WEIGHTS = {
    "screenshot": 1.0,   # highest operator-intent signal
    "note": 0.7,
    "idea": 0.5,
    "event": 0.4,
    "webhook": 0.2,      # auto-fired
}
HALF_LIFE_DAYS = 7
```

**Best-effort contract**: a compute failure must NEVER block rec creation.
`service.create` wraps the call in try/except + log; row commits without
attention fields populated. Frontend treats null as "no signal" + hides
the badge.

**UI surface**: `RxFinanceDetail.tsx` renders a violet "👁️ Operator
attention" tile under the 3-up KPI cards when `attention_score > 0`,
showing per-ticker count breakdowns ("NVDA: 3 screenshots + 1 note · META:
2 notes"). Hidden entirely when score == 0 (respect operator empty-state).

**Design pick**: explicit attention column (plan option B) over composite-
score modulation (option A). Decision-engine changes that aren't visible
are anti-product; the badge teaches the operator *why* this rec ranked
where it did and closes the feedback loop on screenshot effort.

## See also

- Brief: `~/.claude/commands/rx-finance.md`
- Plan: `.claude/plans/rx-finance-panel.md`
- Storage routing: `~/Documents/Sho's Playgroun/rx-meta/DECISIONS-LOG.md` D-045
- Generator (laptop): `~/.claude/commands/rx-finance.md`
