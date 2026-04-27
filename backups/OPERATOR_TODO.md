# Operator-driven snapshot steps

These two snapshot artifacts can't be captured autonomously by Claude — they need your hands on the dashboards/CLI. Complete before starting Phase 1 work.

## 1 · Railway Postgres dump

**Why**: Insurance against Tailscale-sync gaps between laptop and Railway. Laptop dump (already captured) covers most of the data, but recent Railway-originated rows that hadn't synced yet would be lost on a laptop-only restore.

### Option A — Railway CLI (recommended)

```bash
# One-time
brew install railway

# Each snapshot
cd "/Users/shourjosmac/Documents/Claude/TradingView "
railway login
railway link  # select tradingv-production project + Postgres service
railway run --service Postgres -- pg_dump -U postgres -d railway --no-owner --no-acl | gzip > backups/railway-2026-04-27.sql.gz
ls -lh backups/railway-2026-04-27.sql.gz
```

### Option B — Direct psql via Railway public connection string

1. Railway dashboard → Postgres service → **Connect** tab → copy the **psql** connection string (looks like `psql 'postgres://postgres:xxx@xxx.proxy.rlwy.net:PORT/railway'`).
2. Extract the URL portion. Run:
   ```bash
   pg_dump '<paste full URL here>' --no-owner --no-acl | gzip > backups/railway-2026-04-27.sql.gz
   ```
   Note: requires `pg_dump` installed locally (`brew install postgresql@16`).

## 2 · Env-var inventory

**Why**: If CF or Railway loses your env vars (project deletion, account migration), this is the only authoritative copy.

Create `backups/env-inventory-2026-04-27.md` with this structure (already gitignored — file stays local only):

```markdown
# Env-var inventory — 2026-04-27

## Railway service (TradingV)

| Var | Value |
|---|---|
| API_KEY | ***ROTATED-API-KEY*** |
| DATABASE_URL | <auto-injected by Postgres plugin — copy actual value> |
| INSTANCE_NAME | railway |
| KRONOS_ENABLED | true |
| DEBUG_STUB | false |
| MAX_CONCURRENT_JOBS | 1 |
| HF_HUB_CACHE | /data/hf-cache |
| PEER_API_URL | http://<laptop-tailnet-ip>:8000 |
| PEER_API_KEY | ***ROTATED-PEER-KEY*** |
| FRONTEND_ORIGIN | https://tradingv-83b.pages.dev,https://tradingv-83b.pages.dev. |
| TS_AUTHKEY | tskey-auth-... |
| RAILWAY_FALLBACK_ENABLED | false |

## CF Pages project (tradingv)

Production env vars:
| Var | Value |
|---|---|
| VITE_RAILWAY_URL | https://tradingv-production.up.railway.app |
| VITE_RAILWAY_KEY | ***ROTATED-API-KEY*** |
| VITE_LAPTOP_URL | (empty) |
| VITE_LAPTOP_KEY | ***ROTATED-PEER-KEY*** |
| VITE_DEFAULT_BACKEND | railway |
| NODE_VERSION | 20 |
```

How to capture:

- **Railway**: dashboard → service → Variables tab → for each row, copy name + value. Tip: enable "Show values" toggle if hidden.
- **CF Pages**: dashboard → Pages → `tradingv` → Settings → Environment variables → expand each Production var → copy.

Once captured, mark this section done and tell Claude — Phase 0 complete, ready for Phase 1.
