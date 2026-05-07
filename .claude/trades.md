# Trades (manual journal)

Phase 5 of the trust-sprint roadmap. Manual trade entry that closes the prediction → opportunity → trade → outcome loop. Brokerage-API integration explicitly out of scope (single user; integration friction not worth it).

## Schema

```
trades(
  id PK,
  opportunity_id FK→opportunities (SET NULL — opportunity deletion doesn't void trade history),
  ticker, side ENUM('buy'|'sell'),
  qty, entry_price, entry_at,
  exit_price (nullable), exit_at (nullable),
  realized_pnl (nullable),         -- recomputed on update if exit_price set
  fees DEFAULT 0,
  notes_md (nullable Text),
  created_at
)
```

## P&L math

`realized_pnl = (exit_price - entry_price) * qty - fees` for BUY; sign-flipped for SELL. Computed in `app/trades/service.py::_compute_pnl` on every `update_trade` that touches `exit_price`.

## Endpoints

```
GET    /v1/trades?ticker=&opportunity_id=&limit=     items + pnl_summary
POST   /v1/trades                                     log new trade (entry only)
PATCH  /v1/trades/{id}                                update exit, fees, notes
GET    /v1/trades/pnl/by-rule                         per-opportunity-rule attribution
```

`pnl_summary` (returned with the list endpoint):
```
{closed_count, open_count, total_realized_pnl}
```

`pnl/by-rule` joins `trades.opportunity_id → opportunities.rule_id`, aggregates closed-trade P&L per rule. Answers: "If I'd taken every R1 BUY signal, what's my realized P&L?" Only meaningful once enough trades link back to opportunities.

## Files

- `app/trades/models.py` — `Trade`
- `app/trades/service.py` — CRUD, P&L summary, by-rule attribution
- `app/trades/routes.py` — endpoints
- `migrations/versions/0015_trades.py`

## Frontend

`/trades` page:
- Three summary cards: Total P&L, Closed count, Open count.
- Table: ticker, side, qty, entry, exit, P&L (color-coded), entry timestamp, action.
- Open trades have a "Close" button → modal for `exit_price`.
- "Log trade" button → modal form for new entry.
- When navigated to with `?from=<oppId>` (from `/opportunities` → "Acted" button → confirm prompt), the form is prefilled with ticker + side + an opportunity link.

## Why manual

- Single user — no need for brokerage OAuth, position reconciliation, or webhook ingest.
- Forces deliberate tagging (link to opportunity → enables per-rule attribution).
- Trivial to extend later if a brokerage integration becomes worthwhile.

## TV Context enrichment hook

When `PATCH /v1/trades/{id}` flips `exit_price` from null → value
(open → closed transition), `app/trades/service.update_trade` calls
`app/tv_context/service.py:enrich_on_trade_close` in a fresh session.
That helper walks `tv_context_items` captured in `entry_at±24h` for the
same ticker, stamps `tombstone.trades += {trade_id, pnl, win, closed_at}`,
and appends `tv_context_item_id` to `trades.context_refs`.

Idempotent in two layers: `was_closed_before` guard skips the call when a
PATCH only updates fees on an already-closed trade; the helper itself
dedupes on `trade_id` inside `tombstone.trades`. Failures are logged but
never raised — trade-close response is never blocked.

Walkthrough: `GET /v1/tv-context/by-trade/{trade_id}` reads
`trades.context_refs` and returns linked items (active or expired
tombstones).

## Known gaps

- No partial-fill or scale-out support: each row is a single entry/exit pair. If you scale into a position, log multiple trades.
- No FIFO/LIFO matching across trades — `realized_pnl` is just (exit - entry) × qty per row.
- `pnl_by_rule` only counts trades with both `opportunity_id` AND `exit_price` set. Open trades + manually-logged trades (no opportunity) are excluded from rule attribution.
