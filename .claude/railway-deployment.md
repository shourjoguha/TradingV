# Railway deployment notes

Hard-won lessons from getting this stack onto Railway. Read before changing anything build-related.

## Builder

We switched from Railpack to **Dockerfile** (commit Phase B1) so we can install Tailscale inside the container — see Tailscale section below. `railway.toml` declares:

```
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"
```

Historical context (Railpack lessons that still apply if you ever revert):
- **`Procfile` `release:` phase runs at BUILD time, not container start.** DB isn't available, so `alembic upgrade head` fails. **Do not put `release:` in `Procfile`.** Use `railway.toml` `startCommand` (`alembic upgrade head && uvicorn ...`) or Railway's dashboard "pre-deploy command" instead.
- `requirements.txt` is the single install manifest. Optional extras files (`requirements-kronos.txt`) are NOT auto-installed. Fold all runtime deps into `requirements.txt` or add a custom build step.

## Services

| Service | Purpose | Key gotchas |
|---|---|---|
| TradingV (FastAPI) | the app | needs Postgres + volume + Kronos deps installed at build time |
| Postgres | shared DB | `DATABASE_URL` injected automatically — but it's `postgres://`, not `postgresql+asyncpg://`. App must accept either (see `app/core/db.py`). |
| function-bun | unrelated | leave sleeping |

## Required env vars (TradingV service)

```
API_KEY                 — protects /webhook + /v1/* on Railway
DATABASE_URL            — auto-injected by Postgres plugin
INSTANCE_NAME           — "railway"
KRONOS_ENABLED          — true
DEBUG_STUB              — false
MAX_CONCURRENT_JOBS     — 1
HF_HUB_CACHE            — /data/hf-cache (points at the volume, see below)
PEER_API_KEY            — laptop's API_KEY (so Railway can authenticate TO laptop). v1: leave blank (see backlog).
PEER_API_URL            — laptop tunnel URL. v1: intentionally blank — Railway → laptop sync deferred (see .claude/backlog.md).
FRONTEND_ORIGIN         — comma-separated browser origins for CORS (e.g. https://your-app.lovable.dev). Empty falls back to localhost:{3000,5173}.
```

`PEER_*` vars describe the OTHER backend, not yourself.

## Volume — Kronos weights persistence

Kronos weights are ~531MB and re-downloading on every cold start is brutal on time + bandwidth.

1. **Attach a volume** to the TradingV service (NOT the Postgres or function-bun service).
2. **Mount path: `/data`**.
3. **Size: 2GB minimum.** 1GB is too tight — HuggingFace's snapshot_download writes blobs + locks + symlinks, and intermediate state can briefly double the footprint.
4. **Set `HF_HUB_CACHE=/data/hf-cache`** as a service env var.
5. First inference request downloads weights into `/data/hf-cache`. Persists across redeploys forever — re-fetch only when upstream NeoQuasar publishes new weights.

## Vendored dependencies

The Kronos model code lives in `app/kronos/_vendor/kronos_model/`. Upstream Kronos uses absolute imports like `from model.module import *` that ONLY work when the repo is the project root. Vendored, this raises `ModuleNotFoundError: No module named 'model'`.

**Always check vendored code for non-relative imports.** Convert to relative (`from .module import *`) when copying upstream packages into a sub-namespace.

## Diagnostic tips

- `ConstraintSpecMissingError: Kronos runtime deps not installed` is misleading. The underlying cause can be ANY ImportError raised during `_import_runtime()` — torch missing, vendored module path wrong, etc. The error message wraps the original via `from e`, so check Railway logs for the real `ImportError` / `ModuleNotFoundError` line above it.
- Railway → Deployments → click latest → **View Logs** — search for `ImportError` or `Traceback`.
- Build logs and runtime logs are separate tabs — if a deploy is "Active" but routes 500, check runtime logs.

## Build/redeploy checklist

1. Push to `main` — Railway auto-deploys.
2. Confirm latest "Active" deployment SHA matches your commit (Deployments tab). Cache or queueing can lag.
3. After deploy, sanity check:
   ```bash
   curl https://<your-railway-url>/health
   curl https://<your-railway-url>/openapi.json | python3 -c "import sys,json; print(list(json.load(sys.stdin)['paths'].keys()))"
   ```
4. If `/v1/*` routes are missing → old deploy still running. Force redeploy.

## Tailscale tunnel (for Railway → laptop sync)

The container joins the operator's tailnet on boot so it can reach the laptop's `localhost:8000` via tailnet IP / MagicDNS, without exposing the laptop publicly.

### How it's wired

- `Dockerfile` installs Tailscale's official Debian package.
- `tailscale-entrypoint.sh` runs `tailscaled --tun=userspace-networking` (no `/dev/net/tun` / `CAP_NET_ADMIN` needed) then `tailscale up --authkey=$TS_AUTHKEY --hostname=tradingv-railway --ephemeral`. After that it execs `alembic upgrade head && uvicorn ...`.
- If `TS_AUTHKEY` is empty, the script SKIPS Tailscale and boots the app normally. Safe default — pushing the container without provisioning the key won't break anything.

### Operator setup (one-time)

1. Sign up / log in to Tailscale (free personal tier). Install on laptop: `brew install tailscale && sudo tailscale up`.
2. Generate an auth key at https://login.tailscale.com/admin/settings/keys with:
   - **Reusable** ✅ (Railway redeploys re-use it)
   - **Ephemeral** ✅ (stale Railway nodes auto-deregister)
   - **Pre-authorized** ✅ (no manual approval per node)
   - **Tag** (e.g. `tag:railway`)
   - **Expiry** 90 days (rotate quarterly)
3. Set on Railway as a **secret** env var: `TS_AUTHKEY=tskey-auth-...`.
4. (Optional) `TS_HOSTNAME=tradingv-railway` — defaults to that if unset.
5. Redeploy. Logs should show `[entrypoint] Tailscale up. Status:` followed by the tailnet status.
6. From laptop: `tailscale ping tradingv-railway` should succeed.

### Setting `PEER_API_URL` over Tailscale

Once Tailscale is joined, set on Railway:
```
PEER_API_URL=http://<laptop-magicdns>:8000
PEER_API_KEY=<laptop's API_KEY>
```
where `<laptop-magicdns>` is what `tailscale status` shows on your laptop (e.g. `shourjos-mbp.tailxxxxx.ts.net`). Test with: trigger a small job on Railway, then `curl localhost:8000/v1/analysis/jobs?origin=peer` on laptop and confirm the job appears with `origin='peer'`.

### Diagnosing Tailscale issues

- Container logs `[entrypoint] tailscaled failed to start` → check `/tmp/tailscaled.log` via `railway logs`. Most common cause: bad auth key.
- `tailscale status` on Railway shows "expired" → key rotated. Generate new key, update Railway env.
- Laptop can't reach Railway via tailnet → confirm laptop is in the same tailnet (`tailscale status` should list `tradingv-railway`).

## What NOT to do

- Don't put `alembic upgrade head` in `Procfile`'s `release:` phase. (Breaks Railpack builds.)
- Don't keep Kronos deps in a separate `requirements-kronos.txt` — Railpack ignores it. Fold into `requirements.txt`.
- Don't use a 1GB volume "to save cost." HF snapshot_download will OOM the disk mid-pull.
- Don't set `PEER_API_URL` to your own Railway URL. It's the OTHER backend's URL.
- Don't trust the suggested-variables panel — it scrapes `.env.*.example` files in the repo, which contain LAPTOP values. Always edit before adding.
