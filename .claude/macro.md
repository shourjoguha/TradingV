# Macro Workbench — Signal layer (Phase M-1)

Foundation for the regime-aware research workbench. Stores curated macro time-series (yfinance + FRED) and serves ratios computed at query time. Backend-only at v1; frontend lands in M-2 once hypotheses consume this data.

> Read [macro-workbench-brainstorm.md](macro-workbench-brainstorm.md) for the north-star design + the six-phase plan.
> See [decisions/012-macro-workbench-storage-shape.md](decisions/012-macro-workbench-storage-shape.md) for "why a separate `macro_series` table over reusing `ohlcv_bars`".

## Schema

`macro_series` (one row per `(symbol, ts)`):
```
id PK,
symbol TEXT,                  -- 'GC=F', 'WALCL', 'EURUSD=X', etc.
source TEXT,                  -- 'yfinance' | 'fred' | 'manual'
ts DATE,                      -- daily granularity only
value NUMERIC(20, 8),
fetched_at TIMESTAMPTZ,
UNIQUE (symbol, ts),
CHECK (source IN (...))
```

Migration: `migrations/versions/0019_macro_series.py`.

Decisions:
- Daily granularity only — macro queries operate weeks-to-months; intraday is wasted storage.
- One value column — FRED is single-value by nature; for yfinance we store close only. Tickers needing OHLC use the existing `ohlcv_bars` cache.
- `UNIQUE (symbol, ts)` is the idempotency gate. Upserts are dialect-aware (PG `ON CONFLICT DO UPDATE` / SQLite same).
- No `interval` column — all macro is daily.

## Symbol registry

Hand-authored at `app/macro/registry.yaml`. ~30 yfinance symbols + 6 FRED series cover the v1 spec (12 ratios × axes + 9 sector strip + hypothesis-specific names). Editing the file + running a refresh is enough to pick up new symbols — no migration. Symbols not in the registry can't be ingested via `refresh_all` but can still be queried (returns empty if nothing was ever upserted).

Cross-reference: every symbol referenced by a hypothesis under [`.claude/hypotheses/draft/`](hypotheses/draft/) is in the registry.

## Providers

Two implementations, both under `app/macro/providers/`:

- `yfinance_provider.py` — wraps `yfinance.download(...)` in a worker thread (yfinance is sync). Returns close-only.
- `fred_provider.py` — fetches the public FRED CSV endpoint (`fredgraph.csv?id=<series_id>`), no API key. Drops `.` (FRED missing-observation marker).

Add a third source by implementing the `MacroProvider` protocol in `providers/base.py` and wiring it in `service._provider_for()`.

## Service (`app/macro/service.py`)

- `refresh(symbol, source=None, since=None)` — fetch upstream + upsert. Auto-resolves source from registry when not given. Raises `ValueError` for unknown symbols (route → 400).
- `refresh_all()` — walk registry, refresh every symbol, per-symbol try/except so one upstream hiccup doesn't poison the whole tick. Returns `{rows_touched, ok, failed, skipped, failures}`.
- `get_series(symbol, since=None, until=None)` — cached values for one symbol. Default `since` = 5 years ago.
- `compute_ratio(numerator, denominator, since=None, until=None)` — inner-join on date in Python; skips dates where either side is missing or the denominator is 0. Ratios are NOT materialised.

### Chunked upsert
yfinance can return >10k daily bars for old tickers. Postgres caps a single bind list at 32767 parameters; `_upsert_points` chunks rows into batches of 1000 (5 cols × 1000 = 5000 params, well under). Without chunking the upsert blows up live. Tests cover the 5000-row case.

## Routes

```
GET   /v1/macro/series?symbol=&since=&until=                              one symbol's cached values
GET   /v1/macro/ratio?numerator=&denominator=&since=&until=               ratio computed on demand
GET   /v1/macro/spread?minuend=&subtrahend=&since=&until=                 difference computed on demand
POST  /v1/macro/refresh?symbol=                                            manual refresh; default = all
```

### Spread alignment (the weekday-mismatch case)

`/v1/macro/spread` forward-fills the subtrahend within a 7-day window so weekly FRED series that publish on different weekdays (e.g. `MORTGAGE30US` Thursdays vs `WGS10YR` Fridays) line up correctly. Without this, exact-date inner-join produces zero overlap. Tested in `test_compute_spread_aligns_within_window`.

All routes require `verify_api_key`. Empty results return 200 with `points: []` (consistent with `/v1/predictions/by-horizon` empty-state).

## Lifespan ingestion loop

Wired in `app/main.py` lifespan as `macro-ingestion` task, alongside the accuracy evaluator and queue worker. First tick fires immediately on startup (catch-up); subsequent ticks every 24h.

Cancellation-safe; one failed tick logs + continues.

## Verification

```bash
# Tests
source venv/bin/activate && python -m pytest tests/test_macro.py -v

# Manual smoke
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/v1/macro/series?symbol=SPY&since=2026-04-01"
curl -G -H "X-API-Key: $API_KEY" "http://localhost:8000/v1/macro/ratio" \
  --data-urlencode "numerator=GC=F" --data-urlencode "denominator=SPY" --data-urlencode "since=2026-04-01"
curl -X POST -H "X-API-Key: $API_KEY" "http://localhost:8000/v1/macro/refresh"
```

## Known shapes / gotchas

- `BTC-USD` has weekend daily bars; equities don't. Inner-join in `compute_ratio` already handles this — the ratio simply skips weekends.
- FRED daily series include weekends as null. Provider drops null rows pre-upsert.
- yfinance ticker symbol changes (rare but happen) → per-symbol failure, logged, doesn't poison the loop.
- Operator-added typo'd registry symbol → counted under `failed` in refresh stats.

## Storage growth (first tick, 2026-04-30)

38 symbols × full history. ~221k rows. ~30 MB Postgres on disk. No partitioning needed.

## Files

- `app/macro/__init__.py`, `models.py`, `schemas.py`, `service.py`, `routes.py`, `registry.yaml`, `registry.py`
- `app/macro/providers/{__init__,base,yfinance_provider,fred_provider}.py`
- `migrations/versions/0019_macro_series.py`
- `tests/test_macro.py` — 16 tests (idempotency, value updates, window filters, ratio inner-join, ratio zero-denominator, refresh_all fan-out + error isolation, route round-trips, FRED CSV parser, chunked-upsert regression)
- `app/main.py` (lifespan task wiring)
- `app/api/router.py` (router registration)

## Frontend (`/macro`, lazy-loaded)

Three sub-tabs, neumorphic palette preserved, no new chart deps (reuses `lightweight-charts ^4.2.1` already in `package.json`).

- **Overview** — 5 regime panels (Inflation / Growth / Liquidity / Stress / **Inflation regime**) each holding 3-4 sparkline rows. Each row supports three shapes: ratio, single series, or **spread** (a−b, weekday-aligned). Click a row to inline-expand a focused line chart. Each panel and each row carries an `<InfoBubble>` reading from `frontend/src/lib/glossary.ts` so hovering an `(i)` icon reveals the definition without leaving the page.
- **Ratios** — one focused chart at a time with a quick-switch dropdown across all 12 ratios.
- **Sectors** — 9-cell sector-vs-SPY strip. Cell color = Δ% vs window-start (green up / red down / yellow flat). Click to expand chart inline. Cell layout is `truncate`+`overflow-hidden` so long sector labels (e.g. "Discretionary") clip cleanly without bleeding into the next tile, and `<Sparkline showPct={false}>` because the cell already shows its own delta to the left of the sparkline — passing `showPct` was rendering two pcts per tile.

Time-range chips: `1Y / 3Y / 5Y / 10Y / Max`. Default 5Y. Sparklines render at weekly close (cheaper, crisper at small size); focused charts use full daily data.

Sidebar entry placed between Trades and Docs.

Single source of truth for which ratios live where: `frontend/src/lib/macro-views.ts` — edit the array, get a new row in the UI.

Files:
- `frontend/src/pages/Macro.tsx` — page shell + sub-tab routing.
- `frontend/src/components/macro/{Sparkline,RatioChart,RegimePanel,SectorStrip}.tsx`. `<Sparkline>` exposes `showPct?: boolean` (default `true`) so callers that already render a delta beside it (SectorStrip) can opt out and avoid double-rendering.
- `frontend/src/lib/macro-views.ts` — config.
- `frontend/src/hooks/use-api.ts` — `useMacroSeries`, `useMacroRatio`, `useMacroRefresh`.
- `frontend/src/lib/types.ts` — `MacroPoint`, `MacroSeriesResponse`, `MacroRatioResponse`, `MacroRefreshResponse`.

What's deliberately deferred (M-2 territory): hypothesis-aware tagging on ratios, composite "regime label" (single number), event annotations on the timeline.

## What this enables (next phases)

- M-2: hypothesis object + view registry. Reads ratios via `compute_ratio()`. No data-shape coupling.
- M-3: wire macro into Opportunities + Trades — confirming/violating hypothesis tags on rows. Reads via the same service.
- M-4: LLM `/research/ask` endpoint — view-scoped DB context. Same service.
