# Boards (UI: "Watchlists")

Casual ticker lists, distinct from the operational `watchlist` table that drives Kronos predictions. Brainstorm + design in [plans/multi-watchlist-and-quotes.md](plans/multi-watchlist-and-quotes.md).

## What this solves

The original `watchlist` conflated two jobs:
1. **Operational** — drives the daily Kronos schedule (now branded "Roster" in UI).
2. **Cognitive** — operator's casual interest tracking.

Adding to the conflated list silently spawned prediction work the operator may not have wanted. This module separates the cognitive job into its own concept ("boards" in code, "Watchlists" plural in UI). Adding a ticker to a board does NOT spawn predictions — it only registers it for nightly quote refresh.

## Schema

```
boards(
  id UUID PK,
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  created_at, updated_at
)

board_tickers(
  board_id UUID FK → boards.id ON DELETE CASCADE,
  ticker TEXT FK → tickers.symbol ON DELETE CASCADE,
  notes TEXT,
  added_at,
  PRIMARY KEY (board_id, ticker)
)
```

Migration: `migrations/versions/0020_boards_and_quotes.py` — also adds the lightweight quote columns to `ticker_market_data`.

## Quote columns (on `ticker_market_data`)

```
last_close        NUMERIC(20,6)
last_close_at     DATE
pct_1w            NUMERIC(10,4)
quote_fetched_at  TIMESTAMPTZ
```

Powers casual list rows + the macro sector drill-in + (future) Dashboard tiles. Single nightly refresh path — `app/market_data/derived.refresh_one()` was extended to fetch quote data alongside IV/earnings; `refresh_watchlist()` was widened to walk the union of roster + every board's tickers, not just the legacy watchlist.

## Endpoints

```
GET    /v1/boards                          list summaries (id, name, ticker_count, …)
POST   /v1/boards                          create (unique name)
GET    /v1/boards/{id}                     detail + tickers + outer-joined quotes
PATCH  /v1/boards/{id}                     rename / re-describe
DELETE /v1/boards/{id}                     cascade tickers off
POST   /v1/boards/{id}/tickers             add (auto-uppercase, idempotent)
DELETE /v1/boards/{id}/tickers/{ticker}    remove
POST   /v1/boards/{id}/tickers/move        atomic move to target_board_id

GET    /v1/quotes?symbols=A,B,C            bulk read of last_close + pct_1w (lives in market_data routes; powers boards + sector drill-in)
```

All require `X-API-Key`.

## Move semantics

- **Across boards** — atomic; preserves `notes` from the source row when target doesn't already have it.
- **Out of roster** — handled by the existing `/v1/watchlist` endpoints; doesn't stop in-flight Kronos runs.
- **Into roster from a board** — no historical backfill; just normal ticker add.

## Frontend

`/watchlists/:boardId?` — lazy-loaded. Chip selector across boards; ticker rows show last close + 1w Δ%; row click opens the symbol on TradingView; move-to-other-list dropdown; per-row remove + delete-board controls. Page header InfoBubble carries the casual-vs-roster distinction (glossary key `watchlist_concept`).

Sector drill-in: when a sector cell is expanded on `/macro/sectors`, a Top Holdings panel renders below the chart using `frontend/src/lib/sector-holdings.ts` (hardcoded top-10 per ETF) + the same `/v1/quotes` endpoint. Each holding click-outs to TradingView.

## Files

- `app/boards/__init__.py`, `models.py`, `schemas.py`, `service.py`, `routes.py`
- `app/market_data/derived.py` — extended to fetch + store quote data
- `app/market_data/routes.py` — `/v1/quotes` bulk endpoint
- `migrations/versions/0020_boards_and_quotes.py`
- `tests/test_boards.py` — 15 tests covering CRUD, idempotency, move, quote join, route round-trips
- `frontend/src/pages/Watchlists.tsx`
- `frontend/src/lib/sector-holdings.ts` — operator-curated top-10 per sector ETF
- `frontend/src/components/macro/SectorStrip.tsx` — drill-in extension
