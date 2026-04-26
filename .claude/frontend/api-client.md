# API client

## `lib/api.ts`

Tiny wrapper around `fetch`. Adds `X-API-Key`, parses errors as `ApiError` (`status` + `detail`), JSON-encodes bodies.

```ts
apiFetch<T>(path, { method?, body?, backendId? }): Promise<T>
healthCheck(backendId?): Promise<boolean>   // no auth, 5s timeout
```

`ApiError.detail` is the FastAPI `detail` field when present, else status text. Mutations in `use-api.ts` toast `err.detail || err.message`.

## `lib/backend-store.ts`

Two backends, switchable at runtime. localStorage key = `kronos_backend`.

```ts
BACKENDS: Record<'laptop'|'railway', BackendConfig>
getBackendId(): BackendId          // reads localStorage, defaults to 'laptop'
setBackendId(id): void
getBackendConfig(id?): BackendConfig
```

`BackendConfig.baseUrl` for laptop is **empty string** in dev (so requests go to `/v1/...` and Vite proxy handles them). Railway is the absolute URL. Sourced from env:

```
VITE_LAPTOP_URL=     # blank → relative URLs → Vite proxy in dev
VITE_RAILWAY_URL=https://tradingv-production.up.railway.app
VITE_LAPTOP_KEY=<secret>
VITE_RAILWAY_KEY=<secret>
```

`.env.local` gitignored. `.env.example` committed (shape only).

## `vite-env.d.ts`

Types `import.meta.env` for the four `VITE_*` vars. Required because `tsc --noEmit` doesn't pick up Vite's globals otherwise.

## Adding a new backend

1. Add entry to `BACKENDS` map in `backend-store.ts`.
2. Add `BackendId` union member in `lib/types.ts`.
3. Add env vars to `.env.example` + `.env.local`.
4. Add `<SelectItem>` row to `BackendToggle.tsx` (auto-renders from `BACKENDS` already — no UI change needed).

## Don't

- Don't hardcode keys. Always go through env.
- Don't bypass `apiFetch` — it normalises errors and headers.
- Don't add SSR fetches. Pure client.
