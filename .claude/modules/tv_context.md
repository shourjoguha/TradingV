# TradingView Context Layer (`app/tv_context/`)

## Purpose

Single polymorphic ingest table that captures TradingView signals the LLM
otherwise cannot see — Pine-script webhook alerts, hand-drawn chart
screenshots (with optional Claude-vision auto-summary), free-form notes,
TV-Idea URLs, and calendar events. Surfaces them at retrieval time to
`/v1/research/ask` + the daily hypothesis tick via a per-hypothesis
`requires_tv_context` flag.

ADRs: [016-tv-context-no-browser-automation.md](../decisions/016-tv-context-no-browser-automation.md),
[017-tv-context-vision-default-on.md](../decisions/017-tv-context-vision-default-on.md).

## Why this is its own module

`app/alerts/` already persists Pine webhooks for **notification** semantics
(`is_read`, drift digest). `tv_context_items` is for **retrieval** semantics
(dedupe, expiry, retrieval ranking, vision summaries). Webhook ingest fans
out to both: alert row always written; tv_context row deduped within rolling
window.

## Schema

`tv_context_items`:

| Column | Notes |
|--------|-------|
| `id` | UUID PK |
| `kind` | `webhook` \| `screenshot` \| `note` \| `idea` \| `event` |
| `ticker` | nullable; ingest doesn't require one |
| `source` | default `tradingview`; future-proof for other channels |
| `captured_at` | server clock at ingest |
| `expires_at` | category default + per-row override |
| `status` | `active` \| `expired` \| `archived` |
| `payload` | JSON — kind-specific. Webhook stores `alert_type` + `data` + `dedupe_count`; screenshot stores `filename` + `note` + `vision` block; etc. |
| `tombstone` | JSON — populated on expire/archive. Preserves `summary`, vision summary text, related_trade outcomes (Phase 5 enrichment). |
| `vault_path` | screenshot sidecar `.md` location; null otherwise |
| `heavy_blob_dropped` | true after sweep nulls heavy fields |
| `dedupe_key` | `sha256(ticker|alert_type|sorted_payload_json)`; webhooks only |

Sibling tables:
- `hypothesis_tv_context_links` — kept separate from `hypothesis_node_links`
  so neither table needs a nullable composite-PK column.
- `trades.context_refs` — JSON list, populated by trade-close enrichment.
- `hypothesis.requires_tv_context` — gating flag.

## Data flow

```
Pine webhook ──► /webhook ──► save_alert
                                ├─► alerts (notification, no dedupe)
                                └─► tv_context.ingest_webhook (retrieval, deduped)

Operator paste ──► UI (TVContextInbox)
                    ├─► /v1/tv-context/screenshot ──► vault writer + vision pipeline
                    │                              ├─► <vault>/Sources/.../{ticker}_{HMS}_{id}.png
                    │                              └─► <vault>/Sources/.../{ticker}_{HMS}_{id}.md (sidecar w/ vision block)
                    ├─► /v1/tv-context/note
                    ├─► /v1/tv-context/idea
                    └─► /v1/tv-context/event

Research/ask ──► bundle (with hypothesis.requires_tv_context flag)
              ├─► tv_context._check_tv_context for supplied tickers
              └─► if flagged && missing => return status='needs_context' (no LLM call)

Trade close (closed_at written) ──► enrich_on_trade_close
                                  ├─► walks tv_context_items in entry_at±24h
                                  └─► appends trade outcome to each tombstone

Lifespan loop (hourly) ──► expire_sweep
                          ├─► flips status=expired
                          ├─► drops heavy payload (image unlink for screenshots)
                          └─► writes tombstone (summary, recreate_hint, vision_summary)
```

## Retention defaults

| Kind | Default TTL |
|------|-------------|
| webhook | 7 d |
| screenshot | 30 d |
| note | 180 d |
| idea | 180 d |
| event | `event_date + 30 d` |

Override per-row at ingest via `expires_at`. Configurable via
`TV_CTX_RETENTION_*_DAYS` env vars.

## Sync

Outbox kinds added: `tv_context_webhook`, `tv_context_note`,
`tv_context_idea`, `tv_context_event`. Screenshots are NOT replicated —
vault path differs per machine and the binary lives outside the DB.
Receiver: `POST /v1/tv-context/import` (idempotent on `id`).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/tv-context/webhook` | Direct webhook ingest (also fan-out from `/webhook`) |
| POST | `/v1/tv-context/note` | Free-form note |
| POST | `/v1/tv-context/idea` | TradingView idea URL — host validated |
| POST | `/v1/tv-context/event` | Calendar event with date-bound expiry |
| POST | `/v1/tv-context/screenshot` | Multipart image upload, vision auto-summary |
| GET  | `/v1/tv-context/by-ticker/{ticker}` | Per-ticker feed (`?include_expired=true` for tombstones) |
| GET  | `/v1/tv-context/by-trade/{trade_id}` | Walk-through: items linked at trade-close |
| POST | `/v1/tv-context/{id}/archive` | Manual archive — drops heavy payload, keeps tombstone |
| POST | `/v1/tv-context/import` | Peer-side ingest (idempotent on `id`) |
| GET  | `/v1/tv-context/vision-spend?month=YYYY-MM` | Monthly Claude-vision cost tally |

## Trade-close enrichment hook (live)

`PATCH /v1/trades/{id}` that flips `exit_price` from null → value triggers
`tv_context.service.enrich_on_trade_close` in a fresh session, fan-out style
(no rollback impact on the trade response). Re-PATCH on an already-closed
trade is a no-op via `was_closed_before` guard PLUS an idempotency check
inside the helper (`tombstone.trades` dedupe by `trade_id`). Failures are
logged and swallowed — never block the trade close.

## Frontend gating (laptop-only UI)

The TV Context inbox page is gated to `backendId === 'laptop'`. When the
operator selects Railway in the backend toggle, a `TVContextLaptopOnlyBanner`
explains why and points back at the toggle. Sidebar nav link stays visible
on both backends (matches Research page UX). **Backend routes stay mounted
on Railway** so peer outbox replication via `/v1/tv-context/import` keeps
working — only the UI surface is gated.

## Known gaps

- **Auto-flag on hypothesis tick**: a hypothesis with
  `requires_tv_context=True` and zero linked tickers can't be auto-flagged
  during the daily tick because tickers aren't a first-class field on
  `Hypothesis`. Today this is operator-driven via the `tickers` parameter
  on `/v1/research/ask`. Tracked in tech_debt.
- **Vault is laptop-only**. Railway can't view screenshots. Webhook / note /
  idea / event rows DO replicate via outbox. See ADR-014.
- **Vision pricing tracks `app/research/client.py`** via the same
  `CLAUDE_INPUT_COST_PER_MTOK` / `CLAUDE_OUTPUT_COST_PER_MTOK` env vars.
  No tier-pricing handling for cache reads — vision calls don't use prompt
  caching.
- **No automatic re-vision** if operator amends caption after upload.
  Manual flow: archive item, re-upload.
