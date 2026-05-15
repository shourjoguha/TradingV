# ticker_review

Persistent queue of tickers identified by Stage 1 of the video-vision
chart-extraction pipeline (`tools/vault_indexer/ingest/video_vision.py` →
Qwen2-VL structured YAML) that are NOT in the operator's whitelist
(roster + boards + The Street). Phase D of the chart-extraction rollout —
gives the operator a forcing function to enrich their universe with
tickers they keep seeing on screen but haven't tracked yet.

The table is laptop-only; it does not replicate to Railway. The Today
strip + Sunday markdown digest both consume it locally.

## Schema

Single table: `ticker_review_queue` (migration `0028`).

| Column | Type | Purpose |
|---|---|---|
| `id` | int PK | |
| `ticker` | varchar(50) UNIQUE | Uppercase, as emitted by Stage 1 |
| `first_seen_at` | timestamptz | First observation |
| `last_seen_at` | timestamptz | Bumped on every repeat |
| `times_seen` | int | Cross-video observation count |
| `channels` | JSON | Up to last 3 channel slugs |
| `recent_video_ids` | JSON | Up to last 3 video_ids |
| `recent_caption_snippets` | JSON | Up to last 3 captions for context |
| `status` | varchar(32) | `pending` / `added_to_roster` / `added_to_board` / `dismissed` |
| `resolved_at` | timestamptz | |
| `resolved_target` | text | Board id when added to a board |
| `previously_dismissed_at` | timestamptz | Set when a 90d-aged dismissed row resurrects |

Composite index `ix_ticker_review_queue_status_last_seen` on
`(status, last_seen_at DESC)` powers the Today strip + digest queries.
UNIQUE on `ticker` keeps the upsert in `enqueue_or_bump` cheap.

## Endpoints

| Path | Method | Behaviour |
|---|---|---|
| `/v1/ticker-review/queue` | GET | Default returns pending rows with `times_seen >= 2`. `?status=all` lists everything; `?status=dismissed` etc. for archive lookups. |
| `/v1/ticker-review/{id}/resolve` | POST | Body `{action, board_id?}`. Atomically chains: `add_to_roster` → `watchlist.add_entry`; `add_to_board` → `boards.add_ticker` (requires `board_id`); `dismiss` → status update only. |

## Population

`tools/vault_indexer/ingest/youtube_channel.py:ingest_one()` collects
`VisionResult.unknown_tickers` from `process_video`. For each unknown
ticker it derives a caption snippet (first chart_ref matching the
symbol) and calls `service.enqueue_or_bump_sync()`. Best-effort: enqueue
failures never block the draft.

The sync wrapper detects whether an event loop is running and either
schedules on it or runs a fresh `asyncio.run`. Indexer ticks go through
`asyncio.run`; tests that already have a loop pick the schedule path.

## Resolution semantics

Service exposes `resolve(entry_id, action, board_id=None)`:

1. Look up the entry (404 if missing).
2. Chain to the destination surface FIRST (`watchlist.add_entry` or
   `boards.add_ticker`). On chain failure the queue row stays
   `pending` and the exception bubbles up to the route handler.
3. Update status + `resolved_at` + `resolved_target` on success.

## Anti-noise filter

`list_pending` filters `times_seen >= MIN_SEEN` (default 2). Single
mentions stay in the DB but don't surface on the Today strip — protects
the operator against Qwen2-VL one-off hallucinations.

## Re-eligibility window

`_RE_ELIGIBILITY_DAYS = 90`. A dismissed row that's re-encountered:

- **Inside the window** → row updates (channels/snippets/`times_seen`)
  but `status` stays `dismissed`. No re-surface.
- **Outside the window** → row resurrects: `status='pending'`,
  `resolved_at=NULL`, `previously_dismissed_at=<old resolved_at>`. The
  Today strip + digest both render a "previously dismissed YYYY-MM-DD"
  chip so the operator remembers the prior decision.

## Today strip

`frontend/src/components/today/TickerReviewStrip.tsx` queries
`useTickerReviewQueue({ status: 'pending', limit: 50 })` and renders the
first 10 entries. Hidden when the queue is empty. Per-row actions:

- **Add to roster** → POST `add_to_roster`
- **Add to board ▾** → board select + POST `add_to_board`
- **Dismiss** → POST `dismiss`

Mutation invalidates `ticker-review-queue`, `watchlist`, and `boards`
caches so the strip + downstream surfaces refresh in one hop.

## Sunday digest

Daily lifespan loop `ticker_review_digest` (registered in
`app/admin/loops.py`). The loop runs every 24h but only emits markdown
when `datetime.now(NY_TZ).weekday() == 6` (Sunday). Target:
`<VAULT_PATH>/Topics/_ticker-review-queue.md`. Sentinel-bounded so any
operator notes around the auto-block survive regeneration:

```
<!-- ticker-review-queue:auto-start -->
…rendered content…
<!-- ticker-review-queue:auto-end -->
```

Two sections: **Surfaced** (`times_seen >= 2`) + **Below threshold**
(single mentions). Manual fire is available through the admin loops UI.

## Decisions that aren't obvious from code

- **Laptop-only state.** No `sync_outbox` row on writes. The queue is
  operator-instance state; the laptop is the only place ingest writes
  unknown tickers. The Sunday digest goes to the shared vault, so any
  agent on either machine can grep `_ticker-review-queue.md` for a
  historical view.
- **Chain-before-status-update.** Status flip happens only after the
  destination surface accepts the write — prevents lost adds when the
  watchlist insert fails. The queue row stays actionable in that case.
- **`previously_dismissed_at` instead of a parallel "history" table.**
  90d re-eligibility only needs one prior decision date; a separate log
  table would be over-design for the cardinality involved.

## Known gaps / future work

- Bulk-dismiss endpoint when the queue grows beyond ~10 single-mention
  rows. Currently the operator dismisses one at a time.
- "Snooze 30 days" action — between Dismiss and never-acting. Not in
  Phase D; lives in [`../status/backlog.md`](../status/backlog.md).
- Cross-laptop replication for multi-operator setups. Not relevant to
  this single-operator product.

## See also

- [`video_vision.md`](video_vision.md) — Stage 1 / 2 / 3 chain that
  emits `unknown_tickers`.
- [`watchlist.md`](watchlist.md) + [`boards.md`](boards.md) — chained
  destinations for resolutions.
- [`../plans/ok-now-we-have-distributed-anchor.md`](../plans/ok-now-we-have-distributed-anchor.md)
  Phase D — original spec.
