# Frontend architecture

Single-page React SPA. Pure client-side fetch — no SSR, no server actions. Single-user app, key in env.

## Stack

| Concern | Choice |
|---|---|
| Build | Vite 5 |
| Framework | React 18 + TypeScript (strict) |
| Routing | react-router-dom v6 (BrowserRouter) |
| Server state | TanStack Query v5 |
| Styling | Tailwind 3 + shadcn/ui (handwritten primitives, not CLI-installed) |
| Charts | lightweight-charts v4 (candlesticks + line overlays) |
| Toasts | sonner |
| Icons | lucide-react |

## Why Vite (not Next.js)

Brief locked Next.js, but Magic Patterns generated a SPA shell (`App.tsx` + `pages/`, react-router). Forcing Next.js would have meant rewriting routing for App Router. Single user, no SSR benefit, no SEO need — Vite SPA is the right shape. Brief §11 even said "App Router with `'use client'` everywhere is fine," confirming pure-CSR was the intent.

## Layout

```
frontend/
  src/
    main.tsx              # ReactDOM root, QueryClientProvider, BrowserRouter, Toaster
    App.tsx               # Routes
    index.css             # Tailwind + theme tokens (dark mode default)
    vite-env.d.ts         # import.meta.env types
    lib/
      api.ts              # fetch wrapper, X-API-Key, ApiError
      backend-store.ts    # BACKENDS map, localStorage selector
      types.ts            # all server-shape types + UI compat aliases
      utils.ts            # cn() = clsx + tailwind-merge
    hooks/
      use-backend.ts      # useSyncExternalStore selector
      use-api.ts          # all queries/mutations w/ shape adapters
    components/
      Layout.tsx          # sidebar + topbar w/ BackendToggle
      BackendToggle.tsx   # laptop/railway radio + health dot
      ui/                 # shadcn primitives (handwritten)
    pages/                # 8 pages — see pages.md
  vite.config.ts          # dev proxy: /v1 + /health → localhost:8000
  tailwind.config.js
  package.json
```

## Magic Patterns: abandoned

MP was used to bootstrap the initial UI (editor `tvwawai8bwsqvsgygvaque`) but is no longer the source of truth. MP's bundler doesn't ship `lightweight-charts` and doesn't expose `import.meta.env` the way Vite does — keeping it in sync isn't worth it. Local `frontend/` is canonical; preview via `npm run dev` and Chrome at `http://localhost:3000`.

## CORS / dev proxy

Backend has no CORS middleware. Local dev uses Vite proxy (`vite.config.ts`) — frontend calls `/v1/...` and `/health`, Vite forwards to `localhost:8000`. Same-origin from the browser's perspective. See `dev-workflow.md` and `backlog.md` (CORS deferred entry).

Toggling to Railway in the browser **fails** until backend gets CORS — also tracked in backlog.
