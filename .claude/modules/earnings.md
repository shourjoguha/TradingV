# earnings

Rolling earnings calendar for the active universe. Backs the IR YouTube
channel poller's earnings-trigger gate (so we only transcribe earnings
calls on release days) plus a future Today-panel "earnings this week" tile.
Phase 2 of the cost-aware iteration plan.

## Universe

`compute_universe()` returns the union of:

- **Roster** — every `WatchlistEntry.symbol`
- **The Street** — Tier 1 + Tier 2 tickers from the most recent 4 snapshots under `<vault>/The Street/snapshots/`

Capped at **150** tickers (`UNIVERSE_CAP`). Order: roster first, then Street
(deduplicated). Each ticker's `last_universe_at` bumps every refresh tick;
rows whose `last_universe_at` is older than **90 days** (`DEFAULT_TTL_DAYS`)
are purged.

## Provider chain

1. **yfinance** — primary. `Ticker.calendar` → "Earnings Date".
2. **NASDAQ** — fallback (free JSON, polite User-Agent, ~5 req/s).
3. **Stale-date sanity** — if the returned date is more than **7 days** before
   today, treat as miss (yfinance occasionally returns the *previous* quarter).
4. **EDGAR confirm** — when an 8-K Item 2.02 ("Results of Operations and
   Financial Condition") is filed within the last 5 days, set `confirmed_at`.

US-only for the EDGAR confirm path; non-US tickers (TSM, BABA, …) skip it.

## Tiered cadence

`refresh_all(force=False)` skips a ticker if BOTH:
- `fetched_at` within last 7 days, AND
- `expected_at` is more than 14 days in the future (or NULL)

Otherwise refreshes via the provider chain. The lifespan loop runs daily;
the operator can fire `/v1/admin/loops/earnings_calendar/fire` to force a
full refresh.

## Trigger window

`channel_in_trigger_window(earnings_trigger, earnings_dates)` reads the
optional `earnings_trigger` block from `_channel.yaml`:

```yaml
earnings_trigger:
  tickers: [GOOGL, GOOG]   # multi-ticker channels supported
  days_before: 0            # operator-tunable
  days_after: 3             # default 3-day post-release window
```

Returns True if today (NY tz) is within the window for ANY of the listed
tickers. The `youtube_channel.ingest_one` poller calls this after the
existing cadence gate and short-circuits with
`reason: 'earnings_trigger_gate_closed'` outside the window — no feed
fetch, no Whisper transcription. Channels without an `earnings_trigger`
block (newsletters, macro feeds) follow their regular cadence.

## Endpoints

- `GET /v1/earnings/upcoming?days=30` — sorted list for the Today panel.
- `GET /v1/earnings/{ticker}` — single row, 404 if unknown.
- `GET /v1/earnings/` — all rows in the next 180 days.
- Manual refresh routes through the generic admin fire endpoint:
  `POST /v1/admin/loops/earnings_calendar/fire`.

## Files

| File | Purpose |
|---|---|
| `models.py` | `EarningsCalendarRow` ORM (migration `0026_earnings_calendar.py`). |
| `service.py` | `compute_universe`, `refresh_for_ticker`, `refresh_all`, `purge_stale_universe`, `upcoming_earnings`, `in_trigger_window`, `channel_in_trigger_window`. |
| `routes.py` | Three GET endpoints (read-only — admin loop handles fire). |

## Tests

- `tests/test_earnings.py` (14 tests) — universe (cap, roster), provider chain (yfinance, NASDAQ fallback, stale-date), purge, trigger window (NY tz), endpoints (upcoming, get_one, 404).
- `tests/test_earnings_trigger_polling.py` (4 tests) — `youtube_channel.ingest_one` respects the trigger gate; multi-ticker channels fire on either; missing earnings_dates short-circuits.

## Known gaps / future

- **Outbox sync to Railway** is intentionally NOT wired in v1. Today panel
  reads the laptop. Adding a sync_kind=`earnings_calendar` row + Railway
  receiver is a 1-day item if needed.
- **7-day retry** when the trigger window passes without a successful
  Whisper transcription — currently the channel just skips on subsequent
  ticks because the poll cadence handles natural retries. If transcripts
  go missing the operator can flip the block off / on manually.
- **EDGAR confirm** currently looks at the title/summary string of recent
  8-K filings for "2.02" or "Results of Operations". Robust parsing of
  the actual primary doc is deferred (current heuristic is enough for the
  large-cap universe).
