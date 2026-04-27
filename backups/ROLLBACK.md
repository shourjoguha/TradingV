# Rollback to v1.0-pre-trust-sprint

If Phase 1+ trust-sprint changes go sideways, restore the cloud-deployed v1 (CF Pages frontend at `tradingv-83b.pages.dev` + Railway backend) using these artifacts.

Snapshot taken: **2026-04-27**, immediately after laptop-toggle-hide UI fix (commit `615e5d1`).

## Artifacts captured

| Artifact | Location | What it preserves |
|---|---|---|
| Git tag | `v1.0-pre-trust-sprint` (annotated, pushed to origin) | Source code at the snapshot moment |
| Laptop DB dump | `backups/laptop-2026-04-27.sql.gz` (gitignored) | Full schema + data of laptop Postgres |
| Railway DB dump | `backups/railway-2026-04-27.sql.gz` (operator-driven, see below) | Full schema + data of Railway Postgres |
| OpenAPI snapshot | `backups/openapi-2026-04-27.json` (gitignored — too large) | API contract (32 routes) |
| Frontend bundle | `backups/frontend-dist-2026-04-27/` (gitignored) | Built static assets CF was serving |
| Env-var inventory | `backups/env-inventory-2026-04-27.md` (gitignored, operator-driven) | Railway + CF env vars |

**Note:** Laptop and Railway DBs are bidirectionally synced (Tailscale, Phase B1+B2). The laptop dump is functionally a Railway dump modulo unsynced rows in flight. Railway dump is captured separately for paranoia.

## Rollback commands

### 1 · Source code

```bash
cd "/Users/shourjosmac/Documents/Claude/TradingView "
git fetch --tags
git checkout v1.0-pre-trust-sprint
# Or to revert main: git reset --hard v1.0-pre-trust-sprint && git push --force origin main (DESTRUCTIVE)
```

### 2 · Laptop Postgres restore

```bash
# Drop + recreate DB (DESTRUCTIVE — wipes current laptop data)
docker exec -e PGPASSWORD=qjcOg7j-K5GoPrFrC6AhUgr3EGBFqKjz tradingview-laptop-pg \
  psql -U tradingview -d postgres -c "DROP DATABASE IF EXISTS tradingview;"
docker exec -e PGPASSWORD=qjcOg7j-K5GoPrFrC6AhUgr3EGBFqKjz tradingview-laptop-pg \
  psql -U tradingview -d postgres -c "CREATE DATABASE tradingview;"
gunzip -c backups/laptop-2026-04-27.sql.gz | \
  docker exec -i tradingview-laptop-pg psql -U tradingview -d tradingview
```

### 3 · Railway Postgres restore

Operator-driven (requires Railway DATABASE_URL + remote `psql` access):

```bash
# From laptop with Railway DB URL exported
railway run --service Postgres psql < <(gunzip -c backups/railway-2026-04-27.sql.gz)
# OR via Railway dashboard "Connect" tab → copy psql command, pipe gunzip into it
```

### 4 · Frontend rollback

CF Pages keeps deployment history natively:
1. CF dashboard → Pages → `tradingv` → Deployments tab
2. Find deployment for commit `615e5d1` (or whichever maps to tag `v1.0-pre-trust-sprint`)
3. Click `…` → **Rollback to this deployment**

Local artifact `backups/frontend-dist-2026-04-27/` is for manual upload as a last-resort fallback.

### 5 · Env-var restore

Open `backups/env-inventory-2026-04-27.md` (gitignored, operator-captured) and re-paste each variable into the corresponding dashboard (Railway service Variables, CF Pages Settings → Environment variables). Trigger redeploy on each.

## Verify rollback succeeded

```bash
# Backend
curl https://tradingv-production.up.railway.app/health         # 200
curl -H "X-API-Key: <railway-key>" https://tradingv-production.up.railway.app/v1/tickers | head

# Frontend
curl -I https://tradingv-83b.pages.dev/                        # 200

# Laptop
curl http://localhost:8000/health
```

## What this snapshot does NOT cover

- Tailscale auth keys (rotate manually if compromised; not needed for code rollback)
- Kronos model weights (cached at `./hf-cache/` and on Railway volume; not snapshotted — re-download from HuggingFace if lost)
- HuggingFace cache (large, regeneratable)
- `node_modules`, `venv`, `__pycache__` (regenerable)
