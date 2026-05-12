# M-1 — Signal layer (Macro Workbench Phase 1)

> **Status:** ✅ SHIPPED 2026-04-30. See [macro.md](../modules/macro.md) for the as-built doc and [decisions/012](../decisions/012-macro-workbench-storage-shape.md) for the storage-shape ADR.
> **Source-of-truth design:** [macro-workbench-brainstorm.md](macro-workbench-brainstorm.md)
> **Pre-execution backups:**
> - Git tag: `pre-m1-20260430-2130` (pushed)
> - Code pushed through commit `2cfd99b`
> - DB snapshot: `backups/laptop-2026-04-30.sql.gz`

## Goal

Land the data foundation for the macro workbench: ingest, store, and serve a curated set of macro time-series + ratios from yfinance and FRED. Backend-only — no frontend in this phase.

After this phase, an operator can:
- Query any of the 12 ratios + 6 macro series via REST.
- Trust nightly refresh keeps cache populated up to the last-published bar.
- Layer M-2 (hypothesis object) on top without re-shaping data.

Out of scope for M-1: hypothesis object, view registry, LLM endpoint, frontend, 13F/Form-4 ingestion, backtesting.

## Scope summary

| Area | Add | Modify | Touch |
|---|---|---|---|
| DB | `macro_series` table (one migration) | none | none |
| Models | `app/macro/models.py` | none | `app/core/db.py` exports stay |
| Schema | `app/macro/schemas.py` (Pydantic) | none | none |
| Providers | `app/macro/providers/{base,yfinance,fred}.py` | none | none |
| Symbols | `app/macro/registry.yaml` | none | none |
| Service | `app/macro/service.py` (`refresh`, `refresh_all`, `get_series`, `compute_ratio`) | none | none |
| Routes | `app/macro/routes.py` (3 endpoints) | `app/main.py` (mount router + lifespan task) | none |
| Tests | `tests/test_macro.py` | `tests/conftest.py` (model import) | none |
| Docs | `.claude/macro.md` (new module doc) + `CLAUDE.md` table row + `roadmap.md` shipped tracking | none | none |

## Schema — `macro_series`

```sql
CREATE TABLE macro_series (
  id          UUID PRIMARY KEY,
  symbol      TEXT NOT NULL,                  -- e.g. 'GC=F', 'WALCL', 'EURUSD=X'
  source      TEXT NOT NULL,                  -- 'yfinance' | 'fred' | 'manual'
  ts          DATE NOT NULL,                  -- bar date (we only store one observation per day)
  value       NUMERIC NOT NULL,               -- close (yfinance) or value (FRED)
  fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (symbol, ts),
  CHECK (source IN ('yfinance', 'fred', 'manual'))
);
CREATE INDEX ix_macro_series_symbol_ts ON macro_series(symbol, ts DESC);
```

Decisions:
- **Daily granularity only.** Macro queries operate at weeks-to-months; intraday is wasted storage. Keeps schema cleaner than reusing `ohlcv_bars` (which is OHLCV+volume — overkill for FRED).
- **One value column.** FRED is single-value by nature; for yfinance we store *close* only. Anyone needing OHLC for an equity ticker uses the existing `ohlcv_bars` cache — those tickers belong there, not here.
- **`UNIQUE (symbol, ts)`** is the idempotency gate. Ingestion uses `INSERT ... ON CONFLICT DO UPDATE` (Postgres) / `INSERT OR REPLACE` (SQLite tests).
- **No `interval` column.** All macro is daily.

## Symbol registry — `app/macro/registry.yaml`

Hand-authored. Drives `refresh_all`. Twelve ratios decompose into ~16 raw symbols (some shared across ratios) plus six FRED series.

```yaml
# Operator-curated. Adding a symbol = add a YAML entry + run a refresh.
# Ratios are computed at query time, not stored — so no entry per ratio.
yfinance:
  # Inflation axis
  - symbol: GC=F          # gold front-month
  - symbol: HG=F          # copper
  - symbol: CL=F          # WTI crude
  - symbol: SI=F          # silver  (kept for silver/gold ratio if asked later)
  # Growth axis
  - symbol: SPY
  - symbol: RSP
  - symbol: IWM
  - symbol: EEM
  - symbol: EFA
  # Stress axis
  - symbol: HYG
  - symbol: LQD
  - symbol: TLT
  # Sectors (for the 9-cell sector-vs-SPY strip)
  - symbol: XLK
  - symbol: XLF
  - symbol: XLE
  - symbol: XLV
  - symbol: XLI
  - symbol: XLP
  - symbol: XLY
  - symbol: XLU
  - symbol: XLB
  # Currency / dollar
  - symbol: DX-Y.NYB
  - symbol: EURUSD=X
  - symbol: USDJPY=X
  # Hypothesis-specific (LatAm, BTC + MSTR, SaaS)
  - symbol: ILF
  - symbol: EWZ
  - symbol: EWW
  - symbol: BTC-USD
  - symbol: MSTR
  - symbol: OKTA
  - symbol: PATH
  - symbol: IGV

fred:
  # Liquidity / rates / debt — series IDs from FRED
  - id: WALCL              # Fed balance sheet
  - id: M2SL               # M2 money stock
  - id: T10YIE             # 5Y5Y inflation expectations
  - id: WGS10YR            # 10Y Treasury yield
  - id: WGS2YR             # 2Y Treasury yield
  - id: WTREGEN            # Treasury General Account
```

Cross-reference: every symbol referenced by a hypothesis in `.claude/hypotheses/draft/*.md` exists in this registry. Future hypotheses can reference symbols not in registry — refresh will skip them (warn) rather than fail.

## Provider abstraction

Mirrors `app/market_data/providers/`. Two implementations:

- `app/macro/providers/yfinance_provider.py` — wraps yfinance `Ticker.history(period='max', interval='1d')`. Returns close-only. Reuses the existing yfinance dependency.
- `app/macro/providers/fred_provider.py` — uses the public FRED CSV endpoint: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series_id>` (no API key required for CSV downloads). Parses with `csv` stdlib, no new deps.

Each provider exposes:
```python
async def fetch(symbol: str, since: date | None) -> list[tuple[date, float]]
```

The FRED CSV path keeps the dep surface zero — using `fredapi` would require an API key (free but adds operator friction).

## Service — `app/macro/service.py`

```python
async def refresh(symbol: str, source: str | None = None) -> int:
    """Fetch from upstream + upsert. Returns rows touched.
    Auto-detects source from registry if not given.
    Idempotent via UNIQUE(symbol, ts) ON CONFLICT DO UPDATE."""

async def refresh_all() -> dict[str, int]:
    """Walk registry.yaml, refresh every symbol. Per-symbol try/except so
    one upstream hiccup doesn't poison the whole cron tick. Returns
    {'ok': N, 'failed': M, 'skipped': K, 'rows_touched': X}."""

async def get_series(symbol: str, since: date | None = None,
                    until: date | None = None) -> list[dict]:
    """Read cached values for one symbol. Default since = 5 years ago."""

async def compute_ratio(numerator: str, denominator: str,
                        since: date | None = None) -> list[dict]:
    """Compute num/denom on the fly using both symbols' cached values.
    Inner-joins on date. Skips dates where either side is missing."""
```

Why compute ratios at query time, not store: ratios are O(symbols × symbols) to materialize, but operators only watch ~12 of them. Cheaper to compute on demand. Reconsider in M-3 if profile shows latency.

## Lifespan ingestion loop — pattern stolen from `accuracy.evaluator_loop`

```python
# In app/macro/service.py
async def ingestion_loop(*, tick_seconds: int = 24 * 60 * 60,
                         stop_event: asyncio.Event | None = None) -> None:
    """Daily refresh loop. Default interval: 24h. Cancellation-safe."""
```

Wired in `app/main.py` lifespan after `accuracy.evaluator_loop`. Runs once at startup (catch-up) then daily. No first-tick-wait.

## Routes — `app/macro/routes.py`

Mounted at `/v1/macro` in `app/main.py`. All require `verify_api_key` (existing dependency).

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/v1/macro/series` | `symbol`, `since?`, `until?` | `{symbol, source, points: [{ts, value}, ...]}` |
| `GET` | `/v1/macro/ratio` | `numerator`, `denominator`, `since?` | `{numerator, denominator, points: [{ts, value}, ...]}` |
| `POST` | `/v1/macro/refresh` | `symbol?` (single) or empty (all) | `{rows_touched, ok, failed, skipped}` |

Empty result: 200 with `points: []` (consistent with `/v1/predictions/by-horizon` empty-state convention).

## Test plan — `tests/test_macro.py`

Tests with fake providers (monkeypatch — no real network calls; same pattern as `tests/test_analysis.py::_stub_lazy_refresh`):

1. `test_macro_series_upsert_idempotent` — refresh twice, row count stays at one per (symbol, ts).
2. `test_macro_series_upsert_updates_value` — re-refresh with provider returning a different value; cached value updates.
3. `test_get_series_filters_by_since` — insert 30 days, query last 10, assert window.
4. `test_compute_ratio_inner_joins_on_date` — insert two symbols with overlapping + non-overlapping dates, assert ratio only emits where both exist.
5. `test_compute_ratio_skips_zero_denominator` — insert a denominator value of 0, assert no NaN in output (skip the date).
6. `test_refresh_all_continues_on_provider_error` — monkeypatch one provider to raise; assert `failed=1, ok=N-1`.
7. `test_refresh_all_walks_registry` — assert every registry symbol is attempted.
8. `test_route_get_series_returns_payload` — round-trip through HTTP layer.
9. `test_route_compute_ratio_round_trip` — same.
10. `test_route_refresh_requires_auth` — sanity.

Auto-stub at module level via fixture — block real yfinance/FRED.

## Docs to write / touch

- New: [.claude/macro.md](../modules/macro.md) — module doc following the same shape as `accuracy.md` / `predictions.md`. ~80 lines.
- New: [.claude/decisions/012-macro-workbench-storage-shape.md](../decisions/012-macro-workbench-storage-shape.md) — ADR for "separate `macro_series` table over reusing `ohlcv_bars`". Brief.
- Touch: [CLAUDE.md](../../CLAUDE.md) — add row to "module-specific docs" table.
- Touch: [.claude/roadmap.md](../status/roadmap.md) — flip 8a from candidate → active.
- Touch: [.claude/decisions/README.md](../decisions/README.md) — index entry for ADR-012.
- After ship: [.claude/roadmap-shipped.md](../status/roadmap-shipped.md) entry.

## Cross-session continuity

If this session compacts mid-execution, a fresh session can pick up by reading:

1. This file (`.claude/plans/M-1-signal-layer.md`).
2. The brainstorm: [`.claude/macro-workbench-brainstorm.md`](macro-workbench-brainstorm.md).
3. TodoWrite state in the session.
4. `git log` since `pre-m1-20260430-2130` shows what's already landed.

## Verification (post-ship)

```bash
# Backend tests
source venv/bin/activate && python -m pytest tests/test_macro.py -v

# Manual smoke (against running laptop backend)
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/v1/macro/series?symbol=SPY&since=2025-01-01" | jq '.points | length'
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/v1/macro/ratio?numerator=GC%3DF&denominator=SPY&since=2025-01-01" | jq '.points | length'
curl -H "X-API-Key: $API_KEY" -X POST "http://localhost:8000/v1/macro/refresh"
```

## Risks

| Risk | Mitigation |
|---|---|
| FRED CSV endpoint rate-limits or 5xxs | Per-symbol try/except in `refresh_all`; log + skip; retry next tick |
| yfinance schema drift (ticker symbol changes) | Same isolation — per-symbol failures don't poison the loop |
| `BTC-USD` dailies have weekend bars; equities don't | Inner-join on date in `compute_ratio` already handles this |
| Operator adds a typo'd symbol to registry | Per-symbol failure logs warning + counted in `skipped` |
| FRED daily series include weekends as null | Provider drops null rows before upsert |
| Storage growth | ~30 symbols × 365 d/yr × 5 yr = ~55k rows. Tiny. No partitioning needed. |

## Estimated effort

~1 day if this is the focus. Breakdown:
- Schema + migration + model: 30 min
- Providers (both): 1.5 h
- Service: 1 h
- Routes: 30 min
- Lifespan loop wiring: 30 min
- Tests: 1.5 h
- Docs + ADR: 30 min
- Verify: 30 min

Total ~6 h focused.
