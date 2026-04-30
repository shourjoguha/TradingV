# Multi-Watchlist + Lightweight Quotes + Sector Drill-In

> **Status:** Active. Started 2026-05-01.
> **Brainstorm:** chat session 2026-05-01 (after stagflation panel work).
> **Cross-session resume:** read this file → check `git log` since `522bbd6` → next-pending todo identifies where to resume. Each sub-phase commits independently.

## North star

Today's `watchlist` table conflates two jobs:
1. **Operational** — the curated set Kronos predicts daily. Heavy: drives the schedule runner, OHLCV cache, accuracy evaluator, opportunity generator.
2. **Cognitive** — "tickers I'm watching."

Plus the operator wants a third surface: **sector drill-in** — when looking at XLE on macro, see top constituents + last close + 1w Δ%.

This plan splits the three jobs cleanly without bloating the DB.

## Operator-locked decisions (2026-05-01)

- **Single prediction roster** (no plural). Future 1h/1d split is a UI filter, not a backend construct. Backend stays simple.
- **Naming:** rename current `/watchlist` UI → "Roster"; new feature called "Watchlists" (plural) for casual lists.
- **Bundle sector drill-in** with this work — shares the lightweight quote infrastructure.
- **No OHLCV cache for casual list members.** Charts link out to TradingView.
- **One quote-data shape** powers casual lists, sector drill-in, and any future Dashboard tiles.

## Scope summary

| Sub-phase | What | Backend touch | Frontend touch |
|---|---|---|---|
| **MW-1** | Rebrand `/watchlist` → `/roster` in the UI. Backend untouched. | None | Sidebar label + route + page header |
| **MW-2** | Multi-watchlist (casual lists) + lightweight quotes | New `boards` + `board_tickers` tables; extend `ticker_market_data` with `last_close`, `last_close_at`, `pct_1w`; daily cron fills them; CRUD endpoints | New `/watchlists/:id?` page; "Watchlists" entry in Decisions sidebar |
| **MW-3** | Sector drill-in — top-10 holdings per sector ETF | None (hardcoded constants module + reuses MW-2's quote columns) | Expand-cell strip on `/macro/sectors` shows holdings + 1w Δ% |

## Why this shape (architecture rationale)

### Naming: rename UI, keep backend table

`watchlist` table is heavily wired into:
- `app/schedule/runner.py` — drives the daily cron
- `app/sync/*` — cross-laptop replication has `kind='watchlist'`
- `app/predictions/*`, `app/opportunities/*` — implicit dependence
- Tests: `test_schedule.py`, `test_sync_replication.py`

A backend rename is high-blast-radius for low value. Internal name stays `watchlist`; **all UI-facing strings + `/watchlist` route move to "Roster" / `/roster`**. This is the cleanest split: operational meaning stays, semantics aren't muddied.

### New tables for casual lists

```sql
CREATE TABLE boards (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE board_tickers (
  board_id UUID REFERENCES boards(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
  notes TEXT,
  added_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (board_id, ticker)
);
```

Calling them `boards` internally avoids name collision with the operational `watchlist` table. UI calls them "Watchlists" — internal naming is invisible.

`ticker_market_data` (already exists for IV/earnings, Phase 6) gains:
- `last_close NUMERIC` — most recent daily close
- `last_close_at DATE` — date of the close
- `pct_1w NUMERIC` — 1-week percent change
- `quote_fetched_at TIMESTAMPTZ` — last refresh stamp

Single nightly cron tick computes these for every registered ticker. Symmetric with the existing IV/earnings refresh path.

### Sector drill-in

`frontend/src/lib/sector-holdings.ts` — operator-curated map: each sector ETF → top-10 holdings (or however many feel right). Updates rarely; manual is fine. When the sector cell expands, render the top-10 with quote data from `ticker_market_data`.

90 symbols total auto-registered into `tickers` registry on first load (existing `upsert_ticker` handles dupe gracefully). They start showing quote data after the next nightly cron tick.

## Cross-cutting concerns

### Move semantics (operator-locked)

- **Out of roster:** doesn't stop in-flight runs. Sets a future-effective flag — schedule runner skips it on next tick. Existing predictions/accuracy preserved.
  - Mechanism: existing `watchlist.delete` already removes from cron; predictions stay because they live on `prediction_points` keyed by ticker, not by membership.
- **Into roster (from a casual board):** no historical backfill. Roster cron picks up the ticker starting next tick.
- **Across casual boards:** trivial — just move the `board_tickers` row.

### "I don't want to interrupt existing predictions"

Already handled: predictions are recorded, evaluated, and queried regardless of whether the ticker is currently in the roster. The roster only governs *future* schedule fan-out.

### Don't bloat OHLCV

Critical discipline: **board members do NOT trigger OHLCV refresh** the way roster members do. The casual-list quote (`last_close + pct_1w`) is a single yfinance call per ticker per night, not a full bar history. Roster members already get OHLCV anyway via the existing schedule path; no change there.

## File layout

### MW-1 (rebrand)

| File | Change |
|---|---|
| `frontend/src/components/Layout.tsx` | NAV_GROUPS: `Watchlist` → `Roster`, path `/watchlist` → `/roster` |
| `frontend/src/App.tsx` | Route `/watchlist` → `/roster`; legacy redirect |
| `frontend/src/pages/Watchlist.tsx` | Rename internal page header label → "Roster"; description tweaks |
| `.claude/frontend/pages.md` | Update route table |

Backend untouched. Tests untouched (they hit `/v1/watchlist` API which remains).

### MW-2 (boards + quotes)

| File | Change |
|---|---|
| `migrations/versions/0020_boards_and_quotes.py` | Create `boards`, `board_tickers`; add quote columns to `ticker_market_data` |
| `app/boards/__init__.py`, `models.py`, `schemas.py`, `service.py`, `routes.py` | New module |
| `app/market_data/derived.py` | Extend daily refresh to compute `last_close + pct_1w` per ticker |
| `app/api/router.py` | Mount `boards_router` |
| `frontend/src/lib/types.ts` | `Board`, `BoardTicker`, `BoardsResponse` |
| `frontend/src/hooks/use-api.ts` | `useBoards`, `useBoard`, `useCreateBoard`, `useAddTickerToBoard`, `useRemoveTickerFromBoard`, `useDeleteBoard`, `useTickerQuote` |
| `frontend/src/pages/Watchlists.tsx` | New page with tabs per board + add-ticker control |
| `frontend/src/components/Layout.tsx` | New "Watchlists" entry under Decisions |
| `frontend/src/App.tsx` | New route `/watchlists/:boardId?` (lazy) |
| `tests/test_boards.py` | New |

### MW-3 (sector drill-in)

| File | Change |
|---|---|
| `frontend/src/lib/sector-holdings.ts` | Hardcoded top-10 per `XLK / XLF / XLE / XLV / XLI / XLP / XLY / XLU / XLB` |
| `frontend/src/components/macro/SectorStrip.tsx` | Below the expanded chart, render top-10 grid with last close + 1w Δ% |
| `frontend/src/hooks/use-api.ts` | `useTickerQuotes(symbols[])` — batch quote read |

## Verification per phase

### MW-1
- Visit `/roster` → existing watchlist UI renders with new title.
- `/watchlist` redirects to `/roster`.
- Sidebar shows "Roster" under Admin.
- Backend tests: 274/274 still pass (untouched).
- TS clean.

### MW-2
- Create a board via API + UI; add a ticker; see last close + 1w Δ%.
- Sidebar shows "Watchlists" under Decisions.
- Operator can have ≥3 boards; tickers move between via UI.
- Adding to a board does NOT spawn a Kronos run.
- Daily cron extension fills quote columns.
- New tests for boards CRUD + quote refresh.

### MW-3
- `/macro/sectors` → click a sector cell → expand shows top-10 holdings table.
- 1w Δ% colored green/red.
- Click a holding → opens `https://www.tradingview.com/symbols/<EX>-<SYM>/` in new tab.

## Risks

| Risk | Mitigation |
|---|---|
| Renaming UI breaks bookmarks | Legacy redirect `/watchlist` → `/roster` |
| `ticker_market_data` table doesn't exist for casual tickers | Auto-register via existing `upsert_ticker` on first board-add |
| Sector hardcoded list goes stale | Quarterly review item in [backlog.md](../backlog.md) |
| Frontend bundle size on link-out chart | Don't render in-app charts. Link out only. |
| Operator confuses Roster vs Watchlists | Sidebar grouping (Admin vs Decisions) keeps mental separation; first-time onboarding tooltip on Roster ("This list drives Kronos predictions") |

## Cross-session resume protocol

A fresh session reads this file → identifies last-completed sub-phase via `git log --oneline 522bbd6..HEAD` → resumes from the next sub-phase's section above. Each sub-phase ends with a commit whose subject contains "MW-1", "MW-2", or "MW-3" so boundaries are obvious.

If a sub-phase fails verification, document the deviation in a "Known issues" section appended to this file, then either fix forward in the same sub-phase or open a follow-up.

## Estimated effort

| Phase | Estimate |
|---|---|
| MW-1 | ~30 min (rename + redirect + a couple of tests) |
| MW-2 | ~3-4 h (migration, model, service, routes, cron extension, page, tests) |
| MW-3 | ~1-1.5 h (hardcoded data + small UI extension) |
| **Total** | **~5-6 h focused** |

## Open question deliberately deferred

**Auto-promote casual ticker to roster on N views?** No for v1 — operator-driven adds are healthier than usage-driven. Re-evaluate if the operator finds themselves manually promoting frequently.
