# Ticker Labels

Free-form EAV metadata on tickers. JSON-typed values let one table store strings, bools, lists, dicts — anything pyJSON serialises — without per-key migrations.

## Schema
```
ticker_labels(
  id PK, symbol FK→tickers (CASCADE),
  key VARCHAR(64), value JSON,
  created_at, updated_at,
  UNIQUE(symbol, key)
)
```

Index: `(key)` for "all symbols where label X is set" queries.

## Common keys (informal — NOT enforced)
- `sector` (str)
- `capsize` (str: micro|small|mid|large)
- `notes` (str, free-form)
- `insider_buy` (bool)
- `hedge_funds` (list[str])
- `planned_horizon` (str: months|quarters|years)

Frontend can present a curated dropdown for these while still allowing arbitrary keys.

## Routes
- `GET    /v1/tickers/{symbol}/labels` — all labels for ticker
- `PUT    /v1/tickers/{symbol}/labels` `{labels: {key:value, ...}}` — bulk upsert (does NOT remove omitted keys)
- `GET    /v1/tickers/{symbol}/labels/{key}` — fetch one
- `PUT    /v1/tickers/{symbol}/labels/{key}` `{value}` — single upsert
- `DELETE /v1/tickers/{symbol}/labels/{key}` — remove one

Auto-upserts the symbol into `tickers` registry — no separate POST needed for new symbols.

## Filter integration

`GET /v1/watchlist?labels=sector:tech,capsize:large` — AND-filter on watchlist by labels. Empty match returns `count=0` (not 404).

Value parsing in `?labels=`:
- Tries JSON first: `insider_buy:true` → bool, `priority:5` → int.
- Falls back to literal string: `sector:tech` → "tech".

Equality is deserialised in Python (small scale, dialect-portable).

## Cascade
`ON DELETE CASCADE` from `tickers.symbol` — deleting a ticker removes its labels. (Tickers are rarely deleted in practice.)
