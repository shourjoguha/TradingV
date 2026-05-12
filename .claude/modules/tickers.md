# Tickers module (`app/tickers/`)

Symbol registry. Source of truth for the frontend dropdown. Every symbol ever entered persists permanently.

## Schema — `tickers` table
`symbol VARCHAR(50) PK (uppercase, trimmed), asset_class, source, first_seen, last_seen, notes`.

- `asset_class` ∈ `{stock, etf, crypto}`
- `source` ∈ `{alert, manual, analysis}` — who inserted first

## Upsert paths (all idempotent on `symbol`)
1. **Webhook ingestion** — `alerts.save_alert` upserts on every alert (`source=alert`).
2. **Manual add** — `POST /v1/tickers` (single body or `{tickers: [...]}`). `source=manual`.
3. **Analysis submission** — any symbol submitted to `/v1/analysis/run` will auto-upsert (`source=analysis`). *Not yet built — Phase 4.*

## Endpoints (all auth-gated, `/v1/tickers` prefix)
- `GET /v1/tickers?asset_class=&q=&limit=` — list for dropdown
- `GET /v1/tickers/search?q=` — typeahead
- `GET /v1/tickers/{symbol}` — detail
- `POST /v1/tickers` — bulk or single upsert (manual)
- `PATCH /v1/tickers/{symbol}` — override `asset_class` or `notes`

## Asset class inference (`asset_class.py`)
Heuristic, deterministic, case-insensitive. Order:
1. Ends with `-USD`/`-USDT`/`-USDC` → `crypto`
2. In hard-coded known-ETF set (SPY, QQQ, ARK*, sector XLs, leveraged 3x, …) → `etf`
3. Ends with `USDT`/`USDC`/`BUSD`/`BTC`/`ETH` and length > 4 → `crypto`
4. Fallback → `stock`

**Accuracy caveat**: the known-ETF list is hand-curated and incomplete. Users can always override via `PATCH`. Do not trust the heuristic for UI decisions that aren't reversible.

## Deletion
Not implemented. Tickers persist forever per product requirement. Add `DELETE` only on explicit request.
