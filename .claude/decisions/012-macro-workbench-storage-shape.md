# ADR-012: Separate `macro_series` table over reusing `ohlcv_bars`

**Date**: 2026-04-30
**Status**: Accepted

## Context

The Macro Workbench (Phase M-1) needs to store curated macro time-series — yfinance equities/futures/FX/ETFs + FRED economic series — and expose them via `/v1/macro/*`. Two storage options:

- **A · Reuse `ohlcv_bars`** (`symbol, interval, ts, open, high, low, close, volume, amount, provider`).
- **B · New `macro_series` table** (`symbol, source, ts, value`).

## Decision

**B — separate `macro_series` table.** Adds one migration (`0019_macro_series.py`); `ohlcv_bars` untouched.

## Why not reuse `ohlcv_bars`

- **FRED is single-value, not OHLCV.** Series like `WALCL` (Fed balance sheet) have one number per observation. Stuffing it into `close` and leaving `open/high/low/volume` null breaks the table's invariants and the schema's intent.
- **Macro is daily-only by design.** `ohlcv_bars` carries an `interval` column (`1d`, `1h`, `15m`, ...). The macro layer operates at daily resolution and only at daily resolution; a redundant column is noise.
- **Sources differ.** `ohlcv_bars` is provider-tagged (`yfinance` for stocks/ETFs only). FRED isn't OHLCV at all and doesn't fit `ohlcv_bars`'s providers tale. Two distinct ingestion concerns belong in two tables.
- **Refresh cadence differs.** `ohlcv_bars` is refreshed by the schedule runner post-prediction + lazily by the analysis pipeline + on-demand by the accuracy evaluator. Macro refresh is its own daily lifespan task — one table per refresh-owner is cleaner.
- **Downstream queries are simpler.** Macro queries are "value over time"; `ohlcv_bars` queries are "OHLCV over interval". Coupling them forces every macro query to filter `interval = '1d'` and ignore four columns.

## Why not store ratios

Ratios are computed at query time in `compute_ratio(num, denom)`. Twelve canonical ratios × ~30 underlying symbols = the operator only watches a handful at a time. Materializing all ratios is `O(symbols^2)` storage for `O(symbols)` watch interest — not worth the write amplification. With ~30 symbols × ~1.3k bars/symbol on first ingest (~40k rows total today) the inner-join is sub-millisecond on Postgres.

Reconsider if profile shows the join is the bottleneck once M-3 adds a second-by-second status recompute on hypotheses — but until then, computed-on-demand wins.

## Trade-offs we accept

- Two tables + two refresh paths to keep operationally aware of (schedule runner refreshes `ohlcv_bars`; macro lifespan refreshes `macro_series`). Mitigated by giving each one its own module + its own loop name in logs (`accuracy-evaluator`, `macro-ingestion`).
- Slight code duplication between `app/market_data/providers/yfinance_provider.py` (OHLCV variant) and `app/macro/providers/yfinance_provider.py` (close-only variant). Acceptable: the OHLCV variant returns bars; the macro variant returns `(date, value)` pairs. Different return shape → different module is cleaner than a Union.
- A symbol could in principle be in *both* tables (e.g. SPY is in `ohlcv_bars` for analysis pipeline, and in `macro_series` for the macro page). That's intentional — different consumers, different windows, different cadences. The `ohlcv_bars` row is OHLCV; the `macro_series` row is close-only. We don't deduplicate.

## Trigger to revisit

- If a third storage need emerges that's *also* close-only-time-series (e.g. crypto on-chain metrics, sentiment indices), generalise `macro_series` into a more abstract `time_series` table at that point — not before.
- If the close-only/OHLCV split causes more than one bug, reconsider unification.
- If FRED ingestion grows to non-daily series (intraday economic data does exist for some series), revisit the daily-only design.

## Files affected

- `migrations/versions/0019_macro_series.py` — table create.
- `app/macro/models.py` — ORM model.
- `app/macro/service.py` — owner of all writes to the table.
- `app/macro/providers/` — separate from `app/market_data/providers/`.

## Cross-references

- [macro.md](../macro.md) — operational doc.
- [macro-workbench-brainstorm.md](../macro-workbench-brainstorm.md) — full design.
- [market_data.md](../market_data.md) — sibling table for OHLCV.
