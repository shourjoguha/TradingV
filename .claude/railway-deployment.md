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
FRONTEND_ORIGIN         — comma-separated browser origins for CORS (production: https://tradingv-83b.pages.dev,https://tradingv-83b.pages.dev. — both forms; trailing-dot variant is browser FQDN normalization). Empty falls back to localhost:{3000,5173}.
TELEGRAM_BOT_TOKEN      — optional. Bot token from @BotFather. Drift alerts + daily digest no-op until both this AND TELEGRAM_CHAT_ID are set.
TELEGRAM_CHAT_ID        — optional. Integer chat ID from getUpdates after DM-ing the bot.
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

The container joins the operator's tailnet on boot so it can reach the laptop privately, without exposing the laptop publicly.

### Network model: HTTP CONNECT proxy, NOT kernel routing

Railway containers can't get `CAP_NET_ADMIN`, so we run `tailscaled --tun=userspace-networking`. **In userspace mode, tailscaled does NOT install kernel routes** — packets the app sends directly to a tailnet IP go to Railway's default gateway and fail with `ConnectError: Name or service not known` (for MagicDNS) or `Connection timed out` (for raw `100.x.y.z` IPs).

Fix: tailscaled exposes an outbound **HTTP CONNECT proxy** on `:1055` (with SOCKS5 also bound to the same port for tools that prefer it). The entrypoint script exports `HTTP_PROXY` / `HTTPS_PROXY` so all app traffic routes through it. httpx (and requests, curl, etc.) auto-honour these env vars — no app code changes needed.

**Don't set `ALL_PROXY`.** httpx interprets `ALL_PROXY=socks5://...` as a SOCKS5 hint and refuses to start unless `socksio` is installed (we don't ship it). HTTP_PROXY/HTTPS_PROXY (HTTP CONNECT) handle both http:// and https:// targets just fine.

`NO_PROXY` excludes:
- `localhost`, `127.0.0.1` (any in-process loopback)
- `postgres.railway.internal`, `.railway.internal`, `.railway.app` (the DB connection + any Railway-internal lookups)

Without the `NO_PROXY` exemption, `asyncpg` would tunnel through tailscaled and fail on the Railway-internal Postgres host.

### How it's wired

- `Dockerfile` installs Tailscale's official Debian package.
- `tailscale-entrypoint.sh`:
  1. Runs `tailscaled --tun=userspace-networking --outbound-http-proxy-listen=:1055 --socks5-server=:1055`.
  2. `tailscale up --authkey=$TS_AUTHKEY --hostname=tradingv-railway --ephemeral`.
  3. Exports `HTTP_PROXY=http://127.0.0.1:1055`, `HTTPS_PROXY=http://127.0.0.1:1055`, `NO_PROXY=localhost,127.0.0.1,postgres.railway.internal,.railway.internal,.railway.app`. ALL_PROXY intentionally NOT set — see note above.
  4. Execs `alembic upgrade head && uvicorn ...` (the Dockerfile CMD).
- If `TS_AUTHKEY` is empty, the script SKIPS Tailscale entirely (no proxy exports either) and boots the app normally. Safe default — pushing the container without provisioning the key won't break anything.

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
PEER_API_URL=http://<laptop-tailnet-ip-or-hostname>:8000
PEER_API_KEY=<laptop's API_KEY>
```
Either form works because the HTTP proxy resolves names + IPs through tailscaled:
- **Tailnet IP** (recommended for stability): `tailscale ip -4` on laptop → `http://100.x.y.z:8000`. IPs don't change unless you reset the device.
- **MagicDNS hostname**: `tailscale status` row → `http://laptop-name.tailxxxxx.ts.net:8000`. Slightly more readable; works because the HTTP proxy does its own DNS resolution.

Test from inside the running container (Railway → service → shell):
```
curl -sv http://<laptop-tailnet-ip>:8000/health
# Should return {"status":"ok"} via the proxy. NO env var change needed —
# HTTP_PROXY is already exported by the entrypoint.
```

End-to-end test: trigger a small job on Railway, then `curl http://localhost:8000/v1/analysis/jobs` on laptop. Job should appear with `origin='peer'` within ~30s. Railway-side `/v1/sync/outbox?status=completed&limit=5` should show the push as completed (`completed_at` set, `last_error: null`).

### Diagnosing Tailscale issues

- `[entrypoint]` lines missing from runtime logs → Dockerfile ENTRYPOINT bypassed. Don't set `[deploy].startCommand` in `railway.toml`; that overrides ENTRYPOINT. The CMD ENTRYPOINT chain in the Dockerfile is what runs the script.
- `[entrypoint] tailscaled failed to start` → check `/tmp/tailscaled.log` via `railway logs`. Most common cause: bad auth key.
- `tailscale status` on Railway shows "expired" → key rotated. Generate new key, update Railway env.
- `ConnectError: Name or service not known` in `sync_outbox.last_error` → HTTP_PROXY env var didn't get exported (entrypoint didn't run, OR it crashed before the export step). Check runtime logs for `HTTP(S)_PROXY=...` line.
- `ConnectError: Connection timed out` to `100.x.y.z` → tailscaled is up but the HTTP proxy listener isn't bound. Check `/tmp/tailscaled.log` for `outbound-http-proxy-listen` errors; ensure `--outbound-http-proxy-listen=:1055` is on the tailscaled command.
- Postgres connection fails after Tailscale is added → `NO_PROXY` doesn't include the Postgres host. The entrypoint sets `postgres.railway.internal,.railway.internal` — don't strip those.
- `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed` → `ALL_PROXY=socks5://...` got exported. Don't set ALL_PROXY (HTTP_PROXY/HTTPS_PROXY are sufficient — see note above), or `pip install httpx[socks]`.
- Laptop can't see Railway in `tailscale status` → Railway never joined. Means the entrypoint didn't run OR `tailscale up` failed. Check Railway runtime logs.

## What NOT to do

- Don't put `alembic upgrade head` in `Procfile`'s `release:` phase. (Breaks Railpack builds.)
- Don't keep Kronos deps in a separate `requirements-kronos.txt` — Railpack ignores it. Fold into `requirements.txt`.
- Don't use a 1GB volume "to save cost." HF snapshot_download will OOM the disk mid-pull.
- Don't set `PEER_API_URL` to your own Railway URL. It's the OTHER backend's URL.
- Don't trust the suggested-variables panel — it scrapes `.env.*.example` files in the repo, which contain LAPTOP values. Always edit before adding.
