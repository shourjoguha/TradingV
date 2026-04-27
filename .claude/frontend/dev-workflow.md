# Dev workflow

## First-time setup

```bash
cd frontend
cp .env.example .env.local      # then fill in VITE_LAPTOP_KEY + VITE_RAILWAY_KEY
npm install
```

API keys are in the original brief at `/Users/shourjosmac/.claude/plans/use-claude-design-to-lovely-babbage.md` §2. Treat as secrets — `.env.local` is gitignored.

## Daily

```bash
cd frontend
npm run dev                      # http://localhost:3000
```

Backend must be running on `:8000` (`uvicorn app.main:app` from repo root with `.env.laptop` loaded). See [.claude/laptop-setup.md](../laptop-setup.md).

## Build

```bash
npm run build                    # tsc -b && vite build → dist/
```

Must be zero errors. Output ~600 KB JS gzipped to ~180 KB. Code-splitting deferred — single user, page load is fine.

## Type-gen from OpenAPI (optional)

```bash
npm run types                    # writes src/lib/openapi-types.ts
```

Re-run when backend OpenAPI changes. Currently not used by the app — `lib/types.ts` is hand-maintained because hook-level adapters reshape responses anyway. Keep around for future cross-checking.

## Vite proxy

`vite.config.ts` forwards `/v1/*` and `/health` → `http://localhost:8000`. This sidesteps CORS for the laptop backend — frontend calls relative URLs, browser thinks it's same-origin.

`VITE_LAPTOP_URL` must be **empty string** in `.env.local` so `BACKENDS.laptop.baseUrl = ''` and requests stay relative.

When you toggle to Railway, requests become absolute (`https://tradingv-production.up.railway.app/v1/...`). Backend has `CORSMiddleware` now (Phase A1) — allow-list driven by `FRONTEND_ORIGIN` env var on Railway, defaulting to `localhost:{3000,5173}` when unset. Local dev works zero-config.

## Adding a page

1. Create `src/pages/Foo.tsx`.
2. Add route in `src/App.tsx`.
3. Add nav entry in `src/components/Layout.tsx` `NAV` array (path, label, lucide icon).
4. Use existing hooks from `hooks/use-api.ts`; add new ones if needed.

## Cloud deploy → Cloudflare Pages

See `/Users/shourjosmac/.claude/plans/cloudflare-pages-port.md` for the full port plan. (Lovable was evaluated and rejected — incompatible on existing-repo import, build-time `VITE_*` env vars, per-PR previews, header config, and AI editor source-of-truth control. CF Pages handles all five.)

TL;DR: connect repo, root `frontend/`, build `npm run build` → `dist/`, set `VITE_RAILWAY_URL` + `VITE_RAILWAY_KEY` + `VITE_LAPTOP_URL=""` + `VITE_DEFAULT_BACKEND=railway` + `NODE_VERSION=20` on CF; set `FRONTEND_ORIGIN=https://tradingv-83b.pages.dev` on Railway; ship `frontend/public/_redirects` for SPA fallback. Laptop toggle decorative from public-internet browsers; usable when laptop is on the same tailnet (rebuild with `VITE_LAPTOP_URL=http://100.x.y.z:8000`).

## Debugging

- React Query devtools not installed. Open `localStorage` in browser → `kronos_backend` key shows current backend.
- API errors: `ApiError.status` + `.detail`. Network tab shows the raw `X-API-Key` header.
- Hot reload: Vite picks up `.tsx` and `.ts` immediately. Changes to `vite.config.ts` or `.env.local` need restart.
