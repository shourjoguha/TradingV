# Macro Workbench — Signal layer (Phase M-1)

Foundation for the regime-aware research workbench. Stores curated macro time-series (yfinance + FRED) and serves ratios computed at query time. Backend-only at v1; frontend lands in M-2 once hypotheses consume this data.

> Read [macro-workbench-brainstorm.md](../plans/macro-workbench-brainstorm.md) for the north-star design + the six-phase plan.
> See [decisions/012-macro-workbench-storage-shape.md](../decisions/012-macro-workbench-storage-shape.md) for "why a separate `macro_series` table over reusing `ohlcv_bars`".

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

Cross-reference: every symbol referenced by a hypothesis under [`.claude/hypotheses/draft/`](../hypotheses/draft) is in the registry.

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

Three sub-tabs, neumorphic palette preserved. All chart rendering goes through the three-tier infra at `frontend/src/components/charts/` — see **[.claude/frontend/charts.md](../frontend/charts.md)** for the decision table, theme tokens, ChartBuilder usage, and migration history. As of 2026-05-18: lightweight-charts dropped; Plotly is the Tier 2 engine for all expanded views.

- **Overview** — 6 regime panels (Inflation / Growth / Liquidity / Stress / **Inflation regime** / **Yield curve**) each holding 3-5 sparkline rows. Each row supports three shapes: ratio, single series, or **spread** (a−b, weekday-aligned). Click a row to inline-expand a focused line chart. Each panel and each row carries an `<InfoBubble>` reading from `frontend/src/lib/glossary.ts` so hovering an `(i)` icon reveals the definition without leaving the page.
  - **Yield curve panel** (added 2026-05-17 from `Videos/{click-capital, fx-evolution-daily}` vault audit). Rows: `WGS2YR` (2Y) · `WGS10YR` (10Y) · `WGS30YR` (30Y — operator-tracked "all-important 5%" level) · `T10Y2Y` (10Y − 2Y spread, recession leading indicator) · `T10Y3M` (10Y − 3M, NY Fed model input). All FRED. Council + decisions log at `.claude/decisions/macro-yields-rework-2026-05-17/`.
  - **Stress panel** gains `^MOVE` (ICE BofA bond-vol) beside `^VIX` (relabelled to "VIX (equity vol)") for bond-vs-equity vol disambiguation. MOVE operator-flagged as leading indicator (fx-evolution-daily-w19 "first sign bonds market actually cares").
- **Ratios** — Tier-3 `<ChartBuilder>` (2026-05-18). Operator picks ratios from the registry (derived from `ALL_ROWS`), toggles chart type per pane (line / area / log-Y), stacks additional panes via "Add pane". Pane config encodes to `?panes=…` for bookmark/share — see `.claude/frontend/charts.md` URL state format. Default view = single line chart w/ the first ratio (preserves legacy parity for non-power-user flow).
- **Sectors** (rebuilt 2026-05-17, three iterations) — dropdown-driven visualization selector + compact sector-strength grid + always-on drill-in chart. Surface anatomy top-to-bottom:
  1. **View dropdown** (`<select id="sector-view">`) flips between 4 perspectives — one viz mounted at a time:
     - **Cycle phase wheel** (`components/macro/CyclePhaseWheel.tsx`) — pure-SVG 360×360 donut w/ 4 quadrants (Early / Mid / Late / Recession). Current phase highlighted in plum at 0.18 alpha. 9 sector dots placed in their canonical-favored quadrants (Fidelity / SSGA taxonomy); dot radius scales w/ `rsIndexed ∈ [80,120] → [6px, 16px]`. Center callout: `you are here / <phase> / 2s10s <spread> · <trend>`. Phase detection runs `detectCyclePhase(t10y2y)` from the cached `T10Y2Y` FRED series — single-indicator classifier so operator can sanity-check by eye.
     - **Rotation footprint** (`components/macro/RotationFootprintStrip.tsx` → `<BumpChart>`, rebuilt 2026-05-18) — smoothed bump chart, 9 matte identity-color lines whose Y-position is each sector's RS rank (1 = strongest) at each snapshot. Line crossings = leadership swaps. Sector labels mirrored on both Y-axes (left = first-snapshot landing, right = last-snapshot landing). **Per-chart cadence selector** (added 2026-05-18) — `12w · 26w · 1y·mo · 3y·mo · 5y·mo` toggle in header lets operator flip between weekly (recent rotation) and monthly (cyclical / regime rotation, up to 5y). Data ceiling is the page-level time chip — pick 5y there to unlock 5y monthly. Math: `weeklyRankMatrix(seriesBySymbol, periods, daysPerPeriod)`.
     - **Phase confirmation badges** (`components/macro/RegimeConditionalBadges.tsx`) — per-sector verdict matrix tagging each sector as `Confirming ✓` (favored-phase = current AND leading SPY) / `Out-of-phase leader ⚑` (favored ≠ current AND leading — operator-investigate signal) / `Failing canonical ✗` (favored = current AND lagging — breadth-divergence warning) / `Quiet ·`. Sorted by signal priority so signal-rich rows surface first.
     - **Correlation matrix** (`components/macro/CorrelationHeatmap.tsx` → `<Heatmap>` w/ click-drill, rebuilt 2026-05-18) — 9×9 pairwise Pearson on daily log-returns. Cells tinted via `CORRELATION_GRADIENT` (red(-1) → grey(0) → green(+1)) w/ native Plotly colorbar. Header summary shows the selected window + average off-diagonal correlation w/ categorical label (`tight cohesion` / `moderate` / `dispersed`). **Per-chart window selector** (added 2026-05-18) — `30d · 90d · 180d · 1y · 3y · 5y` toggle cascades to both the matrix and the click-drill rolling-pair line. **Click a cell** → rolling Pearson of that pair (at the same window) renders as a `<LineChart>` below; clear-X resets. Math: `correlationMatrix(closesBySymbol, days)` + `rollingPairCorrelation(a, b, days)`.
  2. **Compact sector grid** (`components/macro/SectorStrip.tsx` + `SectorLadderCard.tsx`) — 3-col responsive grid of 9 cards, each showing rank · ticker+label · z-scored RS sparkline · RS-indexed % w/ tone · 14-day momentum chevron (▲/▼/→). Sorted by `rsRankBySymbol` descending; null-rank sectors at bottom. 4px identity left-bar from `SECTOR_IDENTITY_BG` palette. Defensive-crowding cue: when 2+ of `{XLP, XLU, XLV}` crowd top-3, the strip gets a `bg-identity-stress/5` wash w/ 1-line caption.
  3. **Always-on drill-in chart** — auto-selects rank-1 sector on mount via `useEffect`; clicking any grid card swaps the active series. Renders `<RatioChart>` for `<sector>/SPY` + `<SectorHoldings>` top-10 ticker list w/ 1w Δ%. No "Close" button — chart always visible.

All 4 dropdown viz share the same `useMacroRatio` / `useMacroSeries` cache (TanStack 5-min stale) — flipping between views is instant after first load. Yield-curve `RegimePanel` previously pinned above the Sectors view was removed 2026-05-17 (operator: "redundant" — same panel renders on Overview).

Time-range chips: `1Y / 3Y / 5Y / 10Y / Max`. Default 5Y. Sparklines render at weekly close (cheaper, crisper at small size); focused charts use full daily data.

Sidebar entry placed in the Think section (re-ordered 2026-05-17).

Single source of truth for which ratios live where: `frontend/src/lib/macro-views.ts` — edit the array, get a new row in the UI.

**Files** (2026-05-17 expansion):
- `frontend/src/pages/Macro.tsx` — page shell + sub-tab routing + `SectorsTab` w/ view-selector dropdown.
- `frontend/src/components/macro/{Sparkline,RatioChart,RegimePanel}.tsx` — original primitives.
- `frontend/src/components/macro/SectorStrip.tsx` — compact 3-col grid + always-on chart.
- `frontend/src/components/macro/SectorLadderCard.tsx` — single sector grid cell.
- `frontend/src/components/macro/CyclePhaseWheel.tsx` — SVG 4-quadrant cycle wheel.
- `frontend/src/components/macro/RotationFootprintStrip.tsx` — 12-week leadership trail.
- `frontend/src/components/macro/CorrelationHeatmap.tsx` — 9×9 rolling Pearson matrix.
- `frontend/src/components/macro/RegimeConditionalBadges.tsx` — per-sector phase verdict.
- `frontend/src/lib/macro-views.ts` — config + `SECTOR_ETFS` (now `SectorEtf` w/ `defensive: bool`) + `SECTOR_IDENTITY_BG` Tailwind class map + `SECTOR_IDENTITY_HEX` SVG fill map + RS math constants (`RS_LOOKBACK_BASE=252` / `RS_ZSCORE_WINDOW=126` / `RS_MOMENTUM_WINDOW=14` / `RS_MOMENTUM_THRESHOLD=0.005`).
- `frontend/src/lib/sector-strength.ts` — pure-function math: `rsIndexed` / `rsMomentum` / `momentumDir` / `rsZScoreSeries` / `rsRankBySymbol` / `defensiveCrowding` / `weeklyRotationFootprint` / `correlationMatrix` / `latestValue`. All Close-only, all client-side, zero backend cost.
- `frontend/src/lib/sector-cycle.ts` — `CyclePhase` type + `PHASES` metadata (4 quadrant angles + labels + blurbs) + `SECTOR_PHASE` canonical mapping (Fidelity taxonomy) + `detectCyclePhase(t10y2y)` single-indicator classifier.
- `frontend/src/hooks/use-api.ts` — `useMacroSeries`, `useMacroRatio`, `useMacroRefresh`, `useMacroSpread`.
- `frontend/src/lib/types.ts` — `MacroPoint`, `MacroSeriesResponse`, `MacroRatioResponse`, `MacroRefreshResponse`.

**Phase classifier math** (defensible, no proprietary framework):
```
spread > +1.0 AND steepening (Δ12m > 0)  → Early
spread > 0  AND flattening (Δ12m < 0)   → Mid
spread ≤ 0                              → Late
spread > 0 AND was ≤ 0 within 12m       → Recession (re-steepening)
```

**RS math contract**:
```
RS(sector, t)         = Close_sector(t) / Close_SPY(t)
RS-indexed(sector, t) = 100 × RS(t) / RS(t-252)
RS-rank(t)            = argsort_desc(RS-indexed) across 9 sectors
RS-momentum(sector,t) = RS(t) / RS(t-14) - 1, ±0.005 dead zone
RS-zscore(sector,t)   = (RS(t) - μ_126d) / σ_126d  (rolling)
```

**Skipped + logged** in roadmap retros (round 2 + 3): did NOT adopt JdK RS-Ratio/RS-Momentum math (foreign vocabulary — vault has zero RRG content); did NOT add the ladder *alongside* the 9-cell grid (replaced, not accreted). The 4 dropdown viz were all originally deferred in `.claude/plans/now-when-i-use-radiant-yao.md` then opted-in across rounds 2 and 3.

What's deliberately deferred (M-2 territory): hypothesis-aware tagging on ratios, composite "regime label" (single number), event annotations on the timeline.

## What this enables (next phases)

- M-2: hypothesis object + view registry. Reads ratios via `compute_ratio()`. No data-shape coupling.
- M-3: wire macro into Opportunities + Trades — confirming/violating hypothesis tags on rows. Reads via the same service.
- M-4: LLM `/research/ask` endpoint — view-scoped DB context. Same service.
