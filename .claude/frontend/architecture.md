# Frontend architecture

Single-page React SPA. Pure client-side fetch — no SSR, no server actions. Single-user app, key in env.

## Stack

| Concern | Choice |
|---|---|
| Build | Vite 5 |
| Framework | React 18 + TypeScript (strict) |
| Routing | react-router-dom v6 (BrowserRouter) |
| Server state | TanStack Query v5 |
| Styling | Tailwind 3 + shadcn/ui (handwritten primitives, not CLI-installed) — Neumorphism design system (light-only, see [ui-components.md](ui-components.md)) |
| Typography | Plus Jakarta Sans (display, 500-800) + DM Sans (body, 400-700), loaded from Google Fonts |
| Charts | lightweight-charts v4 (candlesticks + line overlays) — neumorphic light theme (see PredictionsByTarget.tsx) |
| Toasts | sonner (with neumorphic classNames in `ui/sonner.tsx`) |
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

## Design system: Neumorphism (Soft UI)

The frontend ships a custom Neumorphism design system — monochromatic cool grey (`#E0E5EC`) with dual opposing RGBA shadows for extruded/inset depth. Light-only (dark mode dropped). Compact-neumorphic density: shadows + radii + palette throughout, but data tables stay tight (`p-3`–`p-6`). Semantic colors (success teal, danger coral, warning amber) kept for P&L / hit-rate / status badges, neumorphic-toned to match the palette.

Tokens live in `tailwind.config.js` (palette + 6 shadow tokens + radii + fonts) and `src/index.css` (CSS vars + body styles + font imports). All `ui/*` primitives implement the physics (extruded at rest, inset on press, hover-lift on buttons, deep-inset on focused inputs). See [ui-components.md](ui-components.md) for primitive details and [pages.md](pages.md) for page-level patterns.

## CORS / dev proxy

Local dev uses Vite proxy (`vite.config.ts`) — frontend calls `/v1/...` and `/health`, Vite forwards to `localhost:8000`. Same-origin from the browser's perspective. See `dev-workflow.md`.

Backend has `CORSMiddleware` driven by `FRONTEND_ORIGIN` env var (CSV of absolute origins; falls back to `localhost:{3000,5173}` when unset). Production deployment at `https://tradingv-83b.pages.dev` (Cloudflare Pages) talks to Railway directly.
