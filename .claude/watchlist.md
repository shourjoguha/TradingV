# Watchlist

The active set of symbols the daily scheduled forecast runner iterates. Distinct from `tickers` (the global registry of every symbol we've ever seen).

## Schema
```
watchlist(symbol PK FK→tickers.symbol, added_at, notes)
```
- v1: single global watchlist (one row per tracked symbol)
- ON DELETE CASCADE on `tickers.symbol` (if registry deletes a symbol, it leaves the watchlist too — but we never delete tickers in practice)

## Routes
- `GET    /v1/watchlist?limit=&offset=` → list
- `POST   /v1/watchlist` `{symbol, notes?}` → add (idempotent; auto-upserts ticker registry)
- `POST   /v1/watchlist/bulk` `{symbols: [...]}` → batch add
- `GET    /v1/watchlist/{symbol}` → fetch one
- `PATCH  /v1/watchlist/{symbol}` `{notes}` → edit notes
- `DELETE /v1/watchlist/{symbol}` → remove (stops future runs; preserves all collected data)

## Removal semantics
Deleting a watchlist row stops future scheduled runs targeting that symbol. It does NOT cascade-delete:
- `analysis_jobs` / `analysis_tasks` — historic forecasts intact
- `prediction_points` — flat forecast rows intact
- `ohlcv_bars` — actuals intact
- `tickers` — registry row intact

## Future expansion
- Multi-watchlist: add `watchlist_id` PK component + `watchlists(id, name)` table — schema migration only, route layer mostly unchanged
- Replicate to Railway: not for v1 (laptop is source of truth). See [backlog.md](backlog.md).
