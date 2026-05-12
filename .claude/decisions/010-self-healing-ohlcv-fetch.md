# ADR-010: Self-healing OHLCV fetch via the accuracy evaluator

**Date**: 2026-04-30
**Status**: Accepted

## Context

`ohlcv_bars` is a persistent Postgres store, not a TTL cache — once a bar lands it stays. But population of that store was only triggered at three moments:

1. `_collect_actuals` runs *after* the daily prediction pipeline (`app/schedule/runner.py`) — pulls a wide yfinance window, but only catches bars that already exist at that instant.
2. Analysis lazy-refresh in `_process_task` — recently shipped; warms cache for the *task's input* (ticker × interval), not for unrelated targets the operator might query later.
3. Manual `POST /v1/market_data/refresh`.

Concrete failure mode: the daily run for target T fires shortly after T-1 23:30 UTC. yfinance has no bar for T at that moment (US market hasn't opened, intraday hasn't elapsed). `_collect_actuals` runs anyway and brings back rows up to T-1. T's bar arrives at the upstream provider hours later — and nothing fetches it until the next day's run, sometimes the day after. The `/predictions/by-horizon` and `/accuracy` views that depend on `_fetch_actual` show "no data" for hours-to-days even though the operator expects them populated.

Two architectural fixes were considered:

- **Read-side lazy refresh** in the by-horizon endpoint (and similar): when an actual is missing on a past target, refresh inline before responding.
- **Fold OHLCV refresh into the accuracy evaluator's hourly loop**: a process that already iterates pending predictions every hour can also be the owner of "fill missing actuals."

## Decision

Fold the refresh into the accuracy evaluator (Option B). Read-paths stay pure readers.

**Mechanism:**
- For each pending `prediction_points` row whose actual bar is absent, call `md_service.refresh(ticker, interval)` once per `(ticker, interval)` per tick (deduped via an in-memory set).
- After refresh, re-query the cache. If the bar landed, evaluate; if not, upsert a row in a new `ohlcv_fetch_misses` table tracking `(ticker, interval, target_ts) → attempts, last_attempt_at`.
- Once `attempts >= MAX_OHLCV_FETCH_ATTEMPTS` (=24, one day of hourly attempts), stop calling the provider for that exact target. Bars that genuinely never publish — delisted tickers, holidays, exchange downtime — stop hammering yfinance forever.

The miss row stays as a forensic artifact: `SELECT * FROM ohlcv_fetch_misses WHERE attempts >= 24 ORDER BY last_attempt_at DESC` lets the operator see what was given up on.

## Why this over read-side lazy refresh

- **Single owner for "fill missing actuals."** The evaluator already iterates pending predictions every hour. Adding refresh to that loop puts the logic in one place, with one well-tested miss-tracking schema.
- **Pure readers stay pure.** `/predictions/by-horizon` is a read endpoint; firing a yfinance call from a page load means a 10s page load on cold cache for 40 watchlist symbols, plus surprise yfinance failures bubbling through to the SPA. Background fill is invisible to the operator and recovers between page loads.
- **Self-healing across endpoints.** Both `/accuracy` (which reads `prediction_accuracy`) and `/predictions/by-horizon` (which reads `ohlcv_bars`) now fill in within an hour of the upstream bar publishing — neither view needed code changes.
- **Diagnostics for free.** The `ohlcv_fetch_misses` table is a built-in answer to "why is this cell still empty?" — read it and you see how many times we tried.

## Trade-offs we accept

- Up to one hour of lag between an upstream bar publishing and it appearing in the UI. Acceptable for a single-operator decision-support tool.
- A new tiny table adds one migration; SQLite + Postgres both fine.
- The `MAX_OHLCV_FETCH_ATTEMPTS` constant is a single global. If different intervals (1h vs 1d) need different caps later, refactor to a per-interval map.
- We don't expose the `ohlcv_fetch_misses` table via an API. Operators read it via `psql` for now.

## What we explicitly didn't do

- **No read-side lazy refresh** in `comparison.by_horizon`. Considered and rejected — adds cold-start latency to the page; doesn't help `/accuracy` which is a separate endpoint.
- **No backfill job** for arbitrary historical bars. The evaluator only acts on `target_ts <= now` rows that already exist in `prediction_points`. Older bars stay where they were.
- **No retry on bars that previously succeeded.** Once `prediction_accuracy` has a row, that target is never re-touched; even if upstream republishes a corrected bar later, we won't see it. Acceptable — yfinance bar revisions are rare.

## Trigger to revisit

- If the watchlist exceeds ~200 symbols, the per-tick refresh storm could rate-limit yfinance. Add jitter or a global concurrency cap on `md_service.refresh`.
- If 1h cadence becomes routine and the 1h evaluator backlog grows, consider tightening `MAX_OHLCV_FETCH_ATTEMPTS` (24 hourly attempts is a lot for an interval that publishes every hour).
- If a second source of missing actuals appears (e.g. baseline closes for opportunities), extend `_try_refresh_actual` to cover those too rather than copy-pasting.

## Files affected

- `app/accuracy/models.py` — new `OhlcvFetchMiss` ORM model.
- `app/accuracy/service.py` — `_try_refresh_actual` helper, `evaluate_pending` calls it; `MAX_OHLCV_FETCH_ATTEMPTS` constant; `ohlcv_refreshed` added to stats dict.
- `migrations/versions/0018_ohlcv_fetch_misses.py` — table create.
- `tests/test_accuracy.py` — three new tests covering refresh-fires, miss-incremented, give-up-after-N.
- `.claude/accuracy.md` — "Self-healing OHLCV fetch" section.
- `.claude/backlog.md` — Unlock #2 marked RESOLVED.

## Cross-references

- [accuracy.md](../modules/accuracy.md) — operational doc.
- [analysis.md](../modules/analysis.md) — sibling lazy-refresh on the input side.
- [predictions.md](../modules/predictions.md) — by-horizon read path that now benefits without changes.
