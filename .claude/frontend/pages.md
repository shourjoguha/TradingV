# Pages

13 routes. All under `src/pages/`. Routing in `src/App.tsx`.

| Route | File | Endpoints | Notes |
|---|---|---|---|
| `/` | `Dashboard.tsx` | `GET /v1/schedule`, `/v1/watchlist?limit=1`, `/v1/analysis/jobs?limit=5`, `/v1/analysis/queue/stats`, `POST /v1/schedule/fire-now` | Cards: schedule status, watchlist size, recent jobs + Queue widget (pending/running counts, hidden when empty). Big "Run now" button. |
| `/watchlist` | `Watchlist.tsx` | `GET/POST/DELETE /v1/watchlist*`, `PUT /v1/tickers/{sym}/labels` | Table + add input + bulk modal + per-row label chips + label filter chip bar. |
| `/schedule` | `Schedule.tsx` | `GET/PUT /v1/schedule`, `POST /v1/schedule/fire-now`, `GET /v1/models` | Form for all `Schedule` fields. tz_name autocomplete. Shows `next_run_at` after save. |
| `/predictions/by-target` | `PredictionsByTarget.tsx` | `GET /v1/predictions/by-target`, `/v1/ohlcv`, `/v1/watchlist`, `/v1/models` | Ticker autocomplete (from watchlist) + target_date + interval + model + fields chips + DOW chips. lightweight-charts candle + N prediction lines. |
| `/predictions/by-horizon` | `PredictionsByHorizon.tsx` | `GET /v1/predictions/by-horizon`, `/v1/watchlist`, `/v1/models` | target_date + horizons multiselect (1..10) + tickers multiselect. Renders grid: rows=tickers, cols=days_ago. Cell colour = (pred-actual)/actual. Grey on null. |
| `/accuracy` | `Accuracy.tsx` | `GET /v1/accuracy/grid`, `/pair`, `/drift`; `POST /v1/accuracy/evaluate`, `/drift/{id}/ack` | Heatmap table (rows=tickers, cols=horizons, cells=hit-rate% color-graded). Cell click → drilldown modal with per-prediction error rows. Drift-alert banner with one-click ack. Window-size selector (10/30/100/500). |
| `/opportunities` | `Opportunities.tsx` | `GET /v1/opportunities`, `PATCH /v1/opportunities/{id}` | Tabs (open/acted/dismissed/expired). Action buttons: Acted (with optional jump to `/trades?from=<oppId>`) + Dismiss (modal with reason). Color-coded predicted move + confidence. |
| `/trades` | `Trades.tsx` | `GET/POST /v1/trades`, `PATCH /v1/trades/{id}` | P&L summary cards (Total / Closed / Open). Table with close-trade modal + log-trade modal. Prefilled from opportunity when navigated with `?from=<oppId>`. |
| `/tickers/:symbol/labels` | `TickerLabels.tsx` | `GET/PUT /v1/tickers/{sym}/labels`, `DELETE /v1/tickers/{sym}/labels/{key}` | Curated key dropdown + free-form. JSON-aware value editor (bool toggle / list builder / string fallback). |
| `/analysis` | `AnalysisJobs.tsx` | `GET /v1/analysis/jobs`, `POST /v1/analysis/run`, `GET/DELETE /v1/analysis/queue*` | Expandable-row history table. Columns: friendly Run summary (sym count · intervals · model), Outcome bar (stacked done/running/ineligible/error counts, lazy-fetched per row on expand), smart When (Today/Yesterday/MMM D), Duration, Open-detail button. Click row to inline-expand task breakdown without leaving the page. Queue card above. Run-now toast: "Queued: <id>". See [queue.md](../queue.md). |
| `/analysis/:jobId` | `AnalysisJobDetail.tsx` | `GET /v1/analysis/jobs/{id}` | Task list + per-task `result_json.forecast` viewer. Mostly used as deep-link / sharing target now that the list page exposes the same task breakdown inline. |
| `/docs/:slug?` | `Docs.tsx` (lazy) | none — markdown bundled at build time | Reference hub. Sticky TOC (h2/h3 scroll-spy). Document switcher (segmented control). Font-size adjuster `A− / A / A+` persisted in `localStorage('docs.fontSize')`. Markdown rendered via `react-markdown` + `remark-gfm` + `rehype-slug`. v1 docs: `metrics` (live) + `how-to-use` (stub). Lazy-loaded so the markdown bundle only ships when the page is opened. Add a doc by dropping `frontend/src/docs/<slug>.md` and registering it in `frontend/src/docs/index.ts`. |
| `/macro/:tab?` | `Macro.tsx` (lazy) | `GET /v1/macro/{series,ratio}`, `POST /v1/macro/refresh` | Macro Workbench signal-layer UI. Three sub-tabs: **Overview** (4 regime panels — Inflation / Growth / Liquidity / Stress — each with 3 sparkline rows; click a row to inline-expand a focused chart), **Ratios** (full-size lightweight-chart with quick-switch dropdown across all 12 ratios), **Sectors** (9-cell sector-vs-SPY strip; cell color = Δ% vs window-start; click to expand). Time-range chips `1Y / 3Y / 5Y / 10Y / Max` (default 5Y). Refresh button posts to backend. Sparklines hand-rolled SVG at weekly resolution; focused charts use `lightweight-charts ^4.2.1` themed for the neumorphic palette. Single source of truth for which ratios live where: `frontend/src/lib/macro-views.ts`. Lazy-loaded. |

## Conventions

- All pages use TanStack Query hooks from `hooks/use-api.ts`. No direct fetch.
- Loading state: `<Skeleton />` from `components/ui/skeleton.tsx`.
- Empty state: text in muted-foreground, not a separate page.
- Dates: send/receive ISO `YYYY-MM-DD`. Convert to local tz at display only.
- Day-of-week filter: Mon=0..Sun=6 (Python convention). Tooltip in UI clarifies.

## Layout

`Layout.tsx` wraps everything: 224px sidebar (nav + Kronos logo), 56px topbar (breadcrumb + `BackendToggle`), scrollable content area max-width 7xl.
