# Hooks

All server interactions go through `hooks/use-api.ts`. Pages never call `apiFetch` directly.

## `use-backend.ts`

`useSyncExternalStore`-based selector for the active backend. Returns `{ backendId, setBackend }`. All API hooks key their query cache by `backendId` so switching backends invalidates everything cleanly.

## `use-api.ts` — shape adapters

The Magic Patterns–generated pages assume convenient shapes that the backend doesn't return verbatim. Hooks transform at the boundary so pages are ergonomic:

| Endpoint | Backend returns | Hook returns |
|---|---|---|
| `GET /v1/watchlist` | `{ entries: [], count: N }` | `{ entries, count, items: entries, total: count }` (alias both) |
| `GET /v1/analysis/jobs` | bare `AnalysisJob[]` | `{ items: [...], total: items.length }` |
| `GET /v1/analysis/jobs/{id}` | `AnalysisJob` with `submitted_at`/`finished_at` | adds `created_at`, `updated_at` aliases + defaults `tickers/intervals/model_ids` to `[]` |
| `GET /v1/ohlcv` | `{ symbol, interval, count, bars: [{ts, open, ...}] }` | `bars[]` with `time = ts.slice(0,10)` (lightweight-charts wants `'YYYY-MM-DD'`, not ISO) |

Why adapt instead of refactoring pages: pages were generated and bulky; hooks are one file. Less surface to drift.

## Standard knobs

- `refetchInterval: 30000` — schedule, dashboard cards, analysis jobs list
- `staleTime: 60000` — watchlist, models, predictions, OHLCV
- 429 handling: `useRunAnalysis` `onError` checks `err.detail === 'at_capacity'` and toasts "Backend busy — retry"

## Mutations

All invalidate the relevant query keys on success and toast outcome. Pattern:

```ts
useMutation({
  mutationFn: (data) => apiFetch(...),
  onSuccess: () => { qc.invalidateQueries({ queryKey: [..., backendId] }); toast.success(...) },
  onError: (err: any) => toast.error(`${err.detail || err.message}`),
})
```

## Adding an endpoint

1. Confirm shape via `curl http://localhost:8000/openapi.json | jq` or `app/<module>/routes.py`.
2. Add type in `lib/types.ts` if not present.
3. Add hook in `use-api.ts` mirroring an existing one.
4. If response shape doesn't match what the page wants, adapt in the `queryFn.then(...)` (don't modify pages).

## Hooks added in Phase 1-5

Backend shape now matches frontend usage closely; new hooks pass through without adapters:

- `useAccuracyGrid({ tickers?, horizons?, model_id?, last_n? })`, `useAccuracyPair({ ticker, horizon_offset, model_id?, limit? })`, `useEvaluateAccuracy()` — for `/accuracy` page.
- `useDriftAlerts()`, `useAckDriftAlert()` — drift banner.
- `useOpportunities({ status?, limit? })`, `useUpdateOpportunity()` — for `/opportunities` page.
- `useTrades({ limit? })`, `useCreateTrade()`, `useUpdateTrade()` — for `/trades` page.

All key by `backendId`, invalidate sibling queries on mutation success, toast outcomes via `sonner`.
