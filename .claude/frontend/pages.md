# Pages

8 routes. All under `src/pages/`. Routing in `src/App.tsx`.

| Route | File | Endpoints | Notes |
|---|---|---|---|
| `/` | `Dashboard.tsx` | `GET /v1/schedule`, `/v1/watchlist?limit=1`, `/v1/analysis/jobs?limit=5`, `POST /v1/schedule/fire-now` | Cards: schedule status, watchlist size, recent jobs. Big "Run now" button. |
| `/watchlist` | `Watchlist.tsx` | `GET/POST/DELETE /v1/watchlist*`, `PUT /v1/tickers/{sym}/labels` | Table + add input + bulk modal + per-row label chips + label filter chip bar. |
| `/schedule` | `Schedule.tsx` | `GET/PUT /v1/schedule`, `POST /v1/schedule/fire-now`, `GET /v1/models` | Form for all `Schedule` fields. tz_name autocomplete. Shows `next_run_at` after save. |
| `/predictions/by-target` | `PredictionsByTarget.tsx` | `GET /v1/predictions/by-target`, `/v1/ohlcv`, `/v1/watchlist`, `/v1/models` | Ticker autocomplete (from watchlist) + target_date + interval + model + fields chips + DOW chips. **Local: lightweight-charts candle + N prediction lines**. MP: inline SVG. |
| `/predictions/by-horizon` | `PredictionsByHorizon.tsx` | `GET /v1/predictions/by-horizon`, `/v1/watchlist`, `/v1/models` | target_date + horizons multiselect (1..10) + tickers multiselect. Renders grid: rows=tickers, cols=days_ago. Cell colour = (pred-actual)/actual. Grey on null. |
| `/tickers/:symbol/labels` | `TickerLabels.tsx` | `GET/PUT /v1/tickers/{sym}/labels`, `DELETE /v1/tickers/{sym}/labels/{key}` | Curated key dropdown + free-form. JSON-aware value editor (bool toggle / list builder / string fallback). |
| `/analysis` | `AnalysisJobs.tsx` | `GET /v1/analysis/jobs`, `POST /v1/analysis/run` | Paginated table. Run-form modal. 429 → toast "Backend busy". |
| `/analysis/:jobId` | `AnalysisJobDetail.tsx` | `GET /v1/analysis/jobs/{id}` | Task list + per-task `result_json.forecast` viewer. |

## Conventions

- All pages use TanStack Query hooks from `hooks/use-api.ts`. No direct fetch.
- Loading state: `<Skeleton />` from `components/ui/skeleton.tsx`.
- Empty state: text in muted-foreground, not a separate page.
- Dates: send/receive ISO `YYYY-MM-DD`. Convert to local tz at display only.
- Day-of-week filter: Mon=0..Sun=6 (Python convention). Tooltip in UI clarifies.

## Layout

`Layout.tsx` wraps everything: 224px sidebar (nav + Kronos logo), 56px topbar (breadcrumb + `BackendToggle`), scrollable content area max-width 7xl.
