# Public Demo Deployment

This branch (`demo`) is the read-only public showcase. Live laptop +
Tailscale + Railway-replica system stays on `main`. The two never share
a deploy.

## Architecture

```
GitHub: branch=demo
   │
   ├── Railway project "tradingv-demo"
   │     - Builder: DOCKERFILE  (railway.toml)
   │     - Source branch: demo
   │     - Env vars: PORT, INSTANCE_NAME=demo, FRONTEND_ORIGIN
   │     - NO secrets, NO DATABASE_URL, NO API keys
   │
   └── Cloudflare Pages project "tradingv-83b" (existing)
         - Re-pointed at branch: demo  (was: main)
         - Build cmd:   cd frontend && npm ci && npm run build
         - Output dir:  frontend/dist
         - Env vars:    see below
```

Cloudflare URL `https://tradingv-83b.pages.dev` becomes the demo URL.

## Railway setup

1. Create a new Railway project (do **not** reuse the live laptop replica).
2. Settings → Source → connect to this repo, branch `demo`.
3. Builder: Dockerfile (declared in `railway.toml`).
4. Env vars (set in dashboard):
   ```
   PORT=8000                                       (auto-injected)
   INSTANCE_NAME=demo
   FRONTEND_ORIGIN=https://tradingv-83b.pages.dev
   ```
   That's it. No `DATABASE_URL`, no `API_KEY`, no `TELEGRAM_*`, no `ANTHROPIC_*`.
5. Healthcheck: `GET /health` returns `200 {"status":"ok","mode":"demo"}`.
6. Deploy. Image is ~80MB and idles cheap.

## Cloudflare Pages setup

If repurposing the existing `tradingv-83b` project:

1. Pages → tradingv-83b → Settings → Builds & deployments.
2. Production branch: change `main` → `demo`.
3. Build command: `cd frontend && npm ci && npm run build`.
4. Build output directory: `frontend/dist`.
5. Environment variables (Production):
   ```
   VITE_DEMO_MODE=true
   VITE_DEMO_API_URL=https://tradingv-production-108c.up.railway.app
   VITE_DEMO_GITHUB_URL=https://github.com/shourjoguha/TradingV/tree/demo
   VITE_DEMO_CONTACT_URL=mailto:guha.shourjo@gmail.com
   VITE_DEMO_VIDEO_OVERVIEW=     # add YouTube IDs once recorded
   VITE_DEMO_VIDEO_TODAY=
   VITE_DEMO_VIDEO_PREDICTIONS=
   VITE_DEMO_VIDEO_MOTION=
   ```
6. Re-deploy.

The committed `frontend/.env.demo` documents these vars but is **not**
loaded by `npm run build` automatically — Cloudflare dashboard env vars
are authoritative.

## Optional: Cloudflare in front of Railway (recommended)

The Railway demo backend is a fixed-size FastAPI serving JSON. Easy to
cache + WAF.

1. Add a CNAME `demo-api.<yourdomain>` → Railway's hostname.
2. Cloudflare Page Rule for `demo-api.<yourdomain>/v1/*`:
   - Cache Level: Cache Everything
   - Edge Cache TTL: 1 hour
   - Rate limiting: 30 req/min/IP
3. Update `VITE_DEMO_API_URL` to `https://demo-api.<yourdomain>`.

## Refreshing the snapshot

Placeholder data is in `demo-data/` already. Replace with live-laptop
data via:

```bash
cd TradingView-demo
source "../TradingView /venv/bin/activate"
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5439/tradingview"
python scripts/bake_demo_snapshot.py
git add demo-data && git commit -m "demo: refresh snapshot $(date +%F)"
git push origin demo
```

Cloudflare and Railway both auto-redeploy on push to `demo`.

## Smoke-test checklist post-deploy

- `curl https://<railway>/health` → 200
- `curl https://<railway>/v1/today` → JSON drift_alerts/research_pending/fresh_signals
- `curl -X POST https://<railway>/v1/research/ask -d '{}'` → 404 (no leak)
- Open `https://tradingv-83b.pages.dev/` → Today page loads, banner shows cutoff date
- Click each tab — Today, Predictions, Motion, About — each renders
- Click a preset Ask pill — answer card shows
- Type a nonsense question — suggestion pills show, no error
- Lighthouse: performance ≥90, no console errors

## Reverting (if needed)

The `main` branch is untouched. To revert Cloudflare:
1. Pages → Settings → Production branch: `demo` → `main`.
2. Re-deploy.

The `demo` branch can be deleted from local + remote without affecting
anything else.
