# Railway deployment notes

Hard-won lessons from getting this stack onto Railway. Read before changing anything build-related.

## Builder

Railway switched from Nixpacks to **Railpack** (auto-selected). It reads `Procfile` and `requirements.txt` differently from Nixpacks:

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

## What NOT to do

- Don't put `alembic upgrade head` in `Procfile`'s `release:` phase. (Breaks Railpack builds.)
- Don't keep Kronos deps in a separate `requirements-kronos.txt` — Railpack ignores it. Fold into `requirements.txt`.
- Don't use a 1GB volume "to save cost." HF snapshot_download will OOM the disk mid-pull.
- Don't set `PEER_API_URL` to your own Railway URL. It's the OTHER backend's URL.
- Don't trust the suggested-variables panel — it scrapes `.env.*.example` files in the repo, which contain LAPTOP values. Always edit before adding.
