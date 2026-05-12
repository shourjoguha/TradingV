# Architecture review — App, end to end

**Date:** 2026-05-09 · **Scope:** What this app actually does + how every layer is wired today
**Format:** Q&A. Body answers carry the load-bearing decision; *italicised paragraphs* hold the deeper technical detail you only need when interrogating the choice.
**Companion:** [`2026-05-02-data-and-models-architecture.md`](2026-05-02-data-and-models-architecture.md) — earlier review, narrower (Kronos + Vault). This review supersedes it for the system-level picture.

---

## Topology — at a glance

```
                                   ┌───────────────────────────┐
                                   │  Operator (single user)   │
                                   │  Browser + Obsidian +     │
                                   │  TradingView.com + Gekko  │
                                   └─────────────┬─────────────┘
                                                 │
                          ┌──────────────────────┴──────────────────────┐
                          ▼                                              ▼
              ┌──────────────────────┐                        ┌────────────────────┐
              │  Frontend SPA        │                        │  Knowledge vault   │
              │  Vite + React :3000  │                        │  ~/Documents/      │
              │  19 routes:          │                        │   knowledge-vault/ │
              │   Today / Ticker Hub │                        │  (canonical, hand- │
              │   Decide / Think /   │                        │   authored MD)     │
              │   Admin              │                        │                    │
              └─────────┬────────────┘                        │  Books/ Newslett./ │
                        │ /v1/* (X-API-Key)                   │  Videos/ Notes/    │
                        ▼                                     │  The Street/       │
              ┌────────────────────────┐                      │  Research/ Sources/│
              │  Laptop FastAPI :8000  │ ◄────── reads ──────►│                    │
              │  PRIMARY backend       │                      │  .indexer/cache.db │
              │  21 modules, gitignored│                      │  (SQLite + vec0)   │
              │  Postgres :5439 docker │                      └────────┬───────────┘
              │  Kronos REAL adapter   │                               │ FS reads
              │  TV Context vision     │                               ▼
              │  Research bundle       │                      ┌────────────────────┐
              │  vault-indexer client  │ ───────── HTTP ─────►│  vault_indexer     │
              │  the_street wrapper    │                      │  SIDECAR :8001     │
              │  Telegram digest       │                      │  uvicorn           │
              │                        │                      │  BGE encoder       │
              │  DISABLE_LIFESPAN... 0 │                      │  /search /traverse │
              │  Lifespan: 11 loops    │                      │  /folder-context   │
              └────┬─────────────┬─────┘                      │  /promote /reload  │
                   │ HTTPS       │ outbox push                │  + extractive      │
                   │             │ via Tailscale userspace    │    teaser (new)    │
                   │             │ proxy :1055                └────────────────────┘
                   │             ▼
                   │   ┌────────────────────────┐                ┌────────────────┐
                   │   │  Railway FastAPI :PORT │                │  Anthropic API │
                   │   │  REPLICA               │                │  Sonnet 4.6:   │
                   │   │  Postgres (Railway)    │                │   research,    │
                   │   │  KRONOS_ENABLED=true   │                │   TV vision    │
                   │   │  Most lifespan loops   │                │  Haiku 4.5:    │
                   │   │   GATED (laptop-only)  │                │   vault auto-  │
                   │   │  /v1/*/import (idemp.) │                │   tag           │
                   │   └────────────────────────┘                └────────────────┘
                   │
                   ▼
           ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
           │  yfinance        │    │  FRED CSV        │    │  TradingView.com │
           │  (OHLCV +        │    │  (macro series)  │    │  (charts +       │
           │   IV + earnings) │    │                  │    │   webhooks)      │
           └──────────────────┘    └──────────────────┘    └──────────────────┘
```

*The frontend speaks only to the laptop FastAPI by default; the operator can flip a sidebar toggle to point at Railway. Nothing speaks to Railway directly except sync replication and the operator's mobile/away access. The vault-indexer is laptop-only and so is the operator's Obsidian vault — Research, Ticker Hub vault chunks, and TV Context UI all degrade gracefully when on the Railway backend.*

---

## §0. What this app actually does

### Q0.1 In one paragraph?

A personal **trading-decision-support** system for a single operator. It runs Kronos candlestick-prediction models on a daily-scheduled watchlist, surfaces rule-based BUY/SELL **opportunities** weighted by historical hit-rate, and lets the operator manually log **trades** that close the loop with per-rule P&L attribution. Around that core it builds an **intelligence layer** — a hand-authored knowledge vault, semantic-search chunks beside every ticker, smart-money snapshots from Gekko, screenshot/note ingest from TradingView.com, and a hypothesis tracker that gets stress-tested by Claude. Two backends keep state in sync: laptop runs the heavy stuff (Kronos, vault-indexer, vision, research), Railway is an always-on read replica for away access.

### Q0.2 What workflow does the IA optimise for?

**Signal → Ticker → Thesis**, plus a morning catch-up.

Concretely:
1. **Today (`/`)** — operator opens the app, sees pending Research approvals from yesterday, drift alerts, fresh signals since last visit, recent TV Context, watchlist deltas. One screen, no hunting.
2. **Click a signal → land on `/ticker/:symbol`** (Ticker Hub) — synthesis page that aggregates predictions, recent TV Context, hypotheses touching the symbol, smart-money mentions from The Street, vault chunks via semantic search, open opportunities, and recent trades. Every ticker mention anywhere in the app deep-links here via a `<TickerLink>` helper.
3. **From there → Theses or Research** for thesis work; **back to /motion/opportunities** to act; **journal in /motion/trades**.

*Prior to the IA reorg the operator had to hop between five separate pages to assemble the same picture for one ticker. The Hub collapses that journey. The intelligence layer (vault, TV Context, The Street, Research) sits as sections inside the Hub instead of as separate top-level pages — they're consumed beside the thing they describe.*

### Q0.3 What is explicitly NOT in scope?

- **Live trading.** The system never places orders. Trades are journaled by hand after the operator executes externally.
- **Multi-user.** Auth is a single shared API key. Watchlist + boards + trades + research are all global, not per-user.
- **Real-time streaming.** OHLCV bars are end-of-period; quotes are nightly. No tick data, no L2.
- **Backtesting infrastructure.** Accuracy is computed forward from real-time predictions only; there's no walk-forward simulator.

---

## §1. Frontend information architecture

### Q1.1 The five top-level surfaces, in priority order:

```
Today                              ← / (replaces Dashboard)
Ticker Hub                         ← /ticker/:symbol (deep-linked, no nav entry)

Decide
  ├── Signals       /motion        opportunities + trades, tabbed
  ├── Predictions   /predictions   by-horizon / by-target / accuracy
  ├── Macro         /macro         Overview / Ratios / Sectors
  └── Watchlist     /watchlist     Roster + Boards, tabbed (Phase 3 reorg)

Think
  ├── Research      /research      Claude Q&A, approve/dismiss queue
  ├── Theses        /theses        hypothesis tracker (Phase 3 added)
  ├── TV Context    /tv-context/:ticker?
  └── The Street    /the-street    smart-money snapshots (Phase 2 added)

Admin (collapsed by default)
  ├── Schedule      /schedule
  ├── Health        /health        analysis jobs + queue
  └── Legacy Dash   /admin/overview
```

*Built in three phases — see [`/.claude/plans/ok-now-we-have-distributed-anchor.md`](/.claude/plans/ok-now-we-have-distributed-anchor.md). Phase 1: nav + Today (drift / pending research / fresh signals). Phase 2: Ticker Hub + The Street + vault proxy + ticker-link helper. Phase 3: Theses + consolidated Watchlist. Phase 4 (Gekko auto-pipeline) is captured in `<vault>/The Street/_source.yaml` but deferred.*

### Q1.2 Today — what does it actually show?

Five strips, each self-hides when empty:

1. **Drift banner** — `useDriftAlerts` (`/v1/accuracy/drift`). Unacked alerts only. Inline Ack button + deep-link to `/predictions/accuracy`.
2. **Pending Research approvals** — `useResearchQueries({ status: 'pending' })`. One-line query + verdict snippet + inline Approve/Dismiss/Detail.
3. **Fresh Signals** — `useOpportunities({ status: 'open' })` filtered client-side by `generated_at > localStorage('today.last_visited_at')`. Sparkle-flagged when fresh.
4. **TV Context strip** — recent items across roster top-8 (8 parallel `useTVContextByTicker` calls; ring on items captured since last visit).
5. **Watchlist delta** — diff vs `localStorage('today.watchlist.snapshot')`. Added/removed chips.

Plus a collapsed RegimeStrip at the bottom and the legacy Dashboard archived at `/admin/overview` for unchanged behaviour.

*"Last visit" is operator-local state in `localStorage`, not server-side. The freshness window resets when the operator unmounts the page (`useEffect` cleanup writes `Date.now()`). Cheap; no migration needed.*

### Q1.3 Ticker Hub — what does it aggregate?

`/ticker/:symbol` — single scroll-anchored screen, no sub-routes:

| Section | Hook(s) | Endpoint(s) |
|---|---|---|
| Header | `useTickerLabels`, `useQuotes`, `useWatchlist` | `/v1/tickers/{sym}/labels`, `/v1/quotes`, `/v1/watchlist` |
| Predictions | `useAccuracyPair` | `/v1/accuracy/pair?ticker=&horizon_offset=1` |
| Smart-money (The Street) | `useStreetTicker` | `/v1/the-street/ticker/{sym}` |
| TV Context | `useTVContextByTicker` | `/v1/tv-context/by-ticker/{sym}` |
| Hypotheses | `useHypotheses({ status: 'active' })` filtered client-side | `/v1/hypotheses` |
| Vault chunks | `useVaultSearch(symbol, k)` | `/v1/vault/search?q=&k=` |
| Open Opportunities | `useOpportunities({ status, ticker })` | `/v1/opportunities?ticker=` |
| Trades | `useTrades({ ticker })` | `/v1/trades?ticker=` |

Every ticker mention elsewhere in the app routes here via the shared `<TickerLink>` component, which also renders an external-link arrow opening the symbol's TradingView.com chart in a new tab.

*Key constraint: the Hub renders ~7 cards of state, but it must not throttle. After throttling-stability work in 2026-05-08, opportunities + trades are server-side filtered (`?ticker=`) and the periodic 60s `refetchInterval` was replaced with `staleTime` so React Query doesn't background-poll for every mounted Hub.*

---

## §2. Forecasting layer — Kronos

### Q2.1 What's the model registry today?

Three NeoQuasar models, declared in `app/kronos/registry.yaml`:

| Model | Params | Context bars | Tokenizer | Status |
|---|---|---|---|---|
| **kronos_base** | 102M | 512 | Kronos-Tokenizer-base | primary |
| kronos_small | 24.7M | 512 | Kronos-Tokenizer-base | lighter alt |
| kronos_mini | 4.1M | 2048 | Kronos-Tokenizer-2k | longest context |

All three carry `unverified: true`. Weights live in **`~/.cache/huggingface/hub`** as of the 2026-05-08 cache consolidation (was `<repo>/hf-cache` before; project-pinned cache deleted). `HF_HUB_CACHE` is no longer set in `.env.laptop`; both backend and vault-indexer share the user-default cache.

*The validator (`app/kronos/validator.py`) is pure logic and exercised by every dropdown + queue submission. The adapter (`app/kronos/real_adapter.py`) lazy-imports torch + huggingface_hub and is invoked only in the queue worker. Validator returns `Eligible` or `Ineligible(reason, message)`; adapter accepts only `Eligible` instances. No bypass.*

### Q2.2 How does daily forecasting actually fire?

```
   /v1/watchlist  ──┐
                    │  symbols
                    ▼
       schedule_config (singleton)
                    │  configurable cron tick
                    ▼
       schedule.runner  ──── submit_run(syms × intervals × models) ──►  queue.enqueue
                                                                            │
                                                                            ▼
                                                                  queue worker (FIFO,
                                                                  single-flight, T1)
                                                                            │
                                                                            ▼
                                                              analysis._process_task per cell
                                                              ├─► validator.check
                                                              │   if Ineligible → close task
                                                              ├─► refresh OHLCV (lazy)
                                                              ├─► adapter.predict
                                                              ├─► explode_task → prediction_points
                                                              └─► sync_outbox(kind=result)
```

*One submission produces N tasks (Cartesian product). Each task is independently completed-or-ineligible; the parent job is `done` once every task resolves. Resubmissions are idempotent on `(prediction_id)` — re-running the same prediction is a no-op.*

### Q2.3 What did stuck-job recovery look like?

After a backend crash on 2026-05-05 left 8 jobs in `running` with all 80 tasks `pending` and no worker alive to drain them, a CLI helper was added: `tools/abort_and_retry_stuck.py`. Lists every running job older than `--min-age-minutes` (default 60), aborts each via `/v1/analysis/jobs/{id}/abort`, then re-submits with the same tickers/intervals/models reconstructed from the task list. `--no-retry` and `--dry-run` flags available. Eight stuck jobs cleared in one pass.

*The abort endpoint is idempotent — it walks tasks, marks `pending`/`running` as `error` with `"aborted: container restarted mid-run"`, sets job to `done`. Already shipped before the helper; the CLI just batches it across the stuck set + re-enqueues.*

---

## §3. Decision layer — Predictions → Opportunities → Trades

### Q3.1 The flow:

```
analysis_tasks.result_json
       │ (auto-explode on completion)
       ▼
prediction_points  (flat materialised table: target_date, horizon, field, predicted_close, ...)
       │
       │ accuracy.evaluator hourly tick
       ▼
prediction_accuracy  (per-row error: error_pct, abs_error_pct, hit_rate, MAPE...)
       │
       │ accuracy.drift_detector every 6h
       ▼
drift_alerts (recent_mape vs all_time_mape ratio threshold)

prediction_points + prediction_accuracy
       │
       │ opportunities.tick hourly (laptop only)
       ▼
opportunities  (rule engine → BUY/SELL signals weighted by historical hit-rate)
       │
       │ operator clicks Acted in /motion/opportunities
       ▼
trades  (manual journal, optional ?from=<oppId> prefill)
       │
       │ on close
       ▼
trades.close → tv_context.enrich_on_trade_close (stamps tombstones with P&L outcome)
              + per-rule P&L attribution (rule_id → win-rate, avg-pnl, expectancy)
```

### Q3.2 Where does the operator actually decide?

**Three signal entry points, one decision page:**
- Today's "Fresh Signals" strip (since-last-visit filter).
- `/motion/opportunities` (full list with status tabs).
- Ticker Hub's "Open opportunities" section (per-symbol).

All three lead to the same `Opportunities` page on click, where Acted/Dismissed mutations land and the optional `?from=` query string carries through to `/motion/trades` for prefilled logging.

*The opportunity → trade prefill is a deliberate one-way edge: the operator can dismiss without journaling, can journal a trade not tied to any opportunity, and can backfill the link later. Status transitions are atomic and idempotent.*

### Q3.3 Health page — what does the OutcomeBar show?

Per-job stacked bar: `done · ineligible · running · error` counts, served eagerly from the `/v1/analysis/jobs` list endpoint (single GROUP BY `(job_id, status)` query, no N+1 detail fetches). A job with 80 tasks now reads `done: 42 · ineligible: 38` instead of just `done · 80`.

*Backend change made 2026-05-08: `AnalysisJobSummary` schema gained five bucket fields, `service.task_buckets_for(job_ids)` aggregates them, route joins. Frontend `JobRow` collapsed view renders the existing `OutcomeBar` component — same one used when expanded, now eager.*

---

## §4. Intelligence layer

### Q4.1 The vault — what's in it?

`~/Documents/knowledge-vault/`, hand-authored Obsidian. Top-level dirs:

| Folder | Class | Decay | Auto-ingest |
|---|---|---|---|
| `Books/` | A (timeless) | none | manual EPUB/PDF → markdown |
| `Newsletters/<author>/` | B (timely) | exp half-life | hourly RSS poll per `_channel.yaml` |
| `Videos/<author>/` | B | exp half-life | YouTube channel poller, Whisper ASR, Shorts filtered |
| `Notes/` | A | none | operator-authored |
| `Topics/` | A | none | optional landing pages |
| `Research/` | A (artifact) | tied to hypothesis | generated by `/v1/research/ask` |
| **`The Street/`** | B | weekly | smart-money snapshots (per `_source.yaml`; v1 manual) |
| `Sources/` | B | per-item | TV.com screenshots + sidecars |

Each folder optionally has an `_index.md` operator-authored vignette that gets prepended to every Research bundle whose evidence falls under that folder. *(See [`/.claude/vault.md`](/.claude/vault.md) for the operator-edit-flow contract.)*

### Q4.2 The vault-indexer — how does it work end to end?

```
Watch ~/Documents/knowledge-vault/         (file mtimes)
       │
       ▼
Parse:  frontmatter (title, author, published_at, horizon_months, tags)
        + body chunked at ~600 tokens, 80 overlap
       │
       ▼
Embed:  BAAI/bge-large-en-v1.5 (1024-d, CPU)
        passages encoded raw; query-side prefix on retrieval
       │
       ▼
Cache:  <vault>/.indexer/cache.db (SQLite + vec0)
        vault_node, vault_chunk, vault_chunk_vec
       │
       ▼
Search: KNN top-(k×4) by cosine, re-rank with decay weight
        decay_weight = exp(-age_months / (horizon/2)) for B-class folders
       │
       ▼
NEW (2026-05-09):  excerpt_sentences = top-2 sentences per chunk
                    selected by reuse of the same BGE encoder, restored
                    to original order. Frontend renders the teaser by
                    default, expandable to full chunk.
```

Sidecar at `:8001`. Endpoints: `/search`, `/folder-context`, `/node/{path}`, `/traverse`, `/reload`, `/promote`, `/apply-renames`, `/regenerate-review`. Backend exposes a thin authenticated proxy at `/v1/vault/*` so the frontend never touches the indexer port directly.

*Decay-aware retrieval is the bridge between "I want timeless wisdom" (Graham) and "I want this week's macro" (Lyn Alden). Both compete in the same KNN pool; the decay weight tilts results without forcing the operator to pre-segment by intent.*

### Q4.3 Research — what does an `/v1/research/ask` call do?

```
POST /v1/research/ask  { query, hypothesis_slugs?, tickers?, force_skip_context_gate? }
       │
       ▼
   bundle.build_bundle:
       ├─ hypothesis cards (slug, axis, claim_type, body_md)
       ├─ vault evidence (k=12 chunks via /search, capped 8k tokens)
       ├─ source_context (folder _index.md vignettes via /folder-context)
       ├─ macro_state (recent yfinance + FRED series)
       └─ accuracy_snapshot (per-ticker 14d hit-rate)
       │
       ▼
   tv_context gate (Phase 4):
       if any flagged hypothesis has requires_tv_context=true
       and supplied tickers lack recent context (7d window)
       → return status='needs_context', no Claude call
       │
       ▼
   Anthropic Sonnet 4.6 with prompt cache (ephemeral on prefix)
   tool: propose_invalidator_update (single, structured)
       │
       ▼
   3-layer DSL validation gate before persisting the proposal
       │
       ▼
   write Research/<query_id>.md  (operator-authored YAML frontmatter
       includes research_query_id for vault-indexer's promote-loop callback)
       │
       ▼
   research_queries audit row + AskResponse with verdict, evidence, action
       │
       ▼
   Operator ticks [x] Approve / [x] Dismiss inside the markdown
       │
       ▼
   vault-indexer's /promote watch loop calls back POST /v1/research/queries/{id}/{approve,dismiss}
       │
       ▼
   On approve: hypothesis invalidator DSL is mutated (Phase 3.7 confirm-modal also gates this from the UI)
```

*The dual approval surface — Confirm-modal in `/research` and checkbox-in-markdown — exists because the operator drafts on phone (markdown) and acts on laptop (modal). Both paths converge on the same backend mutation. Idempotent: re-checking a checkbox or re-clicking the modal is a no-op once `approved_at` is set.*

### Q4.4 TV Context — what is it for?

A polymorphic per-ticker inbox of trading-context items: TradingView webhook alerts, manually-uploaded screenshots, free-form notes, ideas (URLs), events (catalysts). Single table `tv_context_items` with `kind` discriminator. Per-category retention; hourly expire-sweep that drops heavy payloads + writes a tombstone preserving the lightweight metadata.

Two value adds:
- **Vision auto-summary on screenshot ingest** — Claude Sonnet 4.6 summarises the chart, ~$0.012/image at 1024px wide, written to `payload.vision.summary` and a sidecar `.md` that the vault-indexer picks up.
- **Trade-close enrichment** — when a trade closes, the `tv_context.service.enrich_on_trade_close` walks items in `entry_at±24h`, stamps tombstones with P&L outcome, populates `trades.context_refs`. Past-decision walkthrough is then `GET /v1/tv-context/by-trade/{trade_id}`.

*UI is laptop-only because the vault sidecar markdown lives on the operator's local disk; Railway shows a "switch to laptop" banner on the page chrome. Backend routes are mounted on Railway too so peer-replicated `/v1/tv-context/import` keeps working — only the UI is gated.*

### Q4.5 The Street — where does smart-money data come from?

`<vault>/The Street/snapshots/<date>/` per snapshot, mostly markdown writeups for the indexer to embed. Raw TSV/JSON copies live under `data/<date>/`. Channels covered: Insiders (SEC Form 4), Politicians (STOCK Act), Trailblazers (51 fund managers, 13F), Billionaires (32 named, 13F), Options-Bullish (unusual flow with conviction ≥ 50). Whales is excluded (Polymarket non-equity).

Two access paths:
- **CLI:** `python -m tools.the_street.query --ticker META --tier 1 --politician "Cleo Fields"` reads the aggregated `multi-channel-tickers.tsv`. Useful for grep-style lookups.
- **Backend wrapper:** `/v1/the-street/{snapshots, ticker/{sym}, tier/{1|2|3}, politician/{name}, digest/{date}/{ticker}}` thin async-wraps the same query module.

The **digest** endpoint is pre-baked: `tools/the_street/build_digests.py` walks every channel file and emits a single `digests.json` per snapshot date with structured per-channel rows + a copy-paste-friendly Markdown rendering. Backend lazy-builds the file on first read; UI's Tier-table accordion renders the digest with a clipboard-copy button. **No upstream API call** when the operator clicks expand.

*Phase 4 of the IA reorg roadmap is a Playwright auto-scrape that writes new dated folders weekly; the config seam (`<vault>/The Street/_source.yaml`) and gating pattern (`if not is_railway` lifespan loop) are reserved but the script is not built.*

### Q4.6 Hypotheses — what role do they play?

Rolling claim register — "EM ratio breaks above 200 SMA → emerging-market regime", "MSTR mNAV stays > 1.5 through Q3", etc. Each hypothesis has:
- `claim_type ∈ {regime, tactical, single_name, breakout}`
- `axis` (free-form regime tag)
- `invalidator: InvalidatorSpec` — DSL with operations `ratio_below_sma`, `series_above_threshold`, `series_change_pct`, `manual`
- `ttl_months` + `expires_at`
- `requires_tv_context: bool` — opt-in flag that gates `/v1/research/ask` (see §4.3)
- `recent_evaluations: list[HypothesisEvaluation]` — daily tick walks every active hypothesis, evaluates the invalidator against current macro state, transitions status if it fires

UI surface: `/theses` list + detail (Phase 3 added). Inline "Stress this thesis" button posts to `/v1/research/ask` with `hypothesis_slugs=[slug]`, navigates to `/research?id=<query_id>`. Cancel button captures a reason and posts to `/v1/hypotheses/{id}/cancel`.

*The DSL was deliberately kept narrow (4 ops) so the LLM-proposed invalidator updates from Research stay parseable. A fifth op needs a corresponding extension to the validator gate; the rejection rate on Claude proposals stayed around 5% with the current vocabulary.*

---

## §5. Sync + replication

### Q5.1 What's the topology?

```
Laptop FastAPI (PRIMARY)                Railway FastAPI (REPLICA)
     │                                            ▲
     │  outbox-drain loop every 5 min             │
     │  drains to peer's /v1/*/import             │
     │                                            │
     ├─► tickers, watchlist, schedule, labels    ─┤
     ├─► trades, hypotheses                      ─┤  (idempotent receivers,
     ├─► research_queries                        ─┤   keyed on stable IDs;
     ├─► tv_context (webhook/note/idea/event)    ─┤   re-runs are no-ops)
     └─► analysis result_json                    ─┤
                                                  │
   Railway → Laptop:                              │
     ├─► tickers, schedule, watchlist, labels    ─┤
     └─► tv_context (peer-imported alerts)       ─┤
```

The transport is HTTPS over a Tailscale tunnel — Railway runs `tailscale up` at container start with a userspace proxy on `:1055`; httpx (and most HTTP clients) auto-honour `HTTP_PROXY`/`HTTPS_PROXY`. `NO_PROXY` exempts localhost, the Railway-internal Postgres, and `*.railway.app` so the DB connection isn't tunnelled.

*Outbox is a SQL table (`sync_outbox`) with `kind`, `payload_json`, `status`, `attempts`, `next_retry_at`. The drain loop respects exponential backoff and removes drained rows after a 7-day retention. Screenshots are intentionally NOT replicated — the vault path is laptop-local. Past-decision walkthroughs from Railway show metadata only; they hyperlink to the laptop screenshot.*

### Q5.2 What's gated to laptop only?

After the 2026-05-05 Railway cost cut, **9 of 11 lifespan loops** are gated by `INSTANCE_NAME != 'railway'`:

| Loop | Cadence (laptop) | Cadence (Railway) |
|---|---|---|
| accuracy_evaluator | hourly | OFF |
| drift_detector | every 6h | OFF |
| digest (Telegram) | daily | OFF |
| market_data_derived (IV, earnings) | daily | OFF |
| opportunities tick | hourly | OFF |
| macro ingestion | daily | OFF |
| hypotheses tick (TTL + invalidator) | daily | OFF |
| research_weekly (Claude stress-test) | weekly | OFF |
| queue_worker (FIFO drain) | continuous | OFF |
| tv-context expire-sweep | hourly | daily |
| sync-outbox drain | 5-min batched | hourly purge only |

*Operator must set `INSTANCE_NAME=railway` on the Railway dashboard for the gate to actually fire. Without that env var the gates are no-ops and Railway runs everything (the original $25/mo state). With it, expected bill is $5-8/mo; the architecture leaves Railway as a thin always-on read replica + ingestion endpoint while the laptop owns compute.*

---

## §6. Cross-cutting trade-offs

### Q6.1 Why decay-aware retrieval inside the indexer instead of date-filter at query time?

Because the operator's queries don't carry a date filter — they ask "what does my vault know about META" and the answer should mix Graham's chapter on margin of safety (timeless) with Lyn Alden's last newsletter (urgent) without the operator pre-selecting which they want. Decay weight on the score does that automatically: the newsletter ranks higher today than three months ago, the chapter ranks the same forever.

*The half-life is `horizon_months / 2` per node, falling back to `default_horizon_months=6` for B-class folders without explicit frontmatter. A B-class file can opt out (timeless override) by setting `horizon_months: null` in frontmatter; an A-class file can opt in by giving an explicit horizon. No flag is global; everything is per-file.*

### Q6.2 Why a sidecar process for the indexer instead of a module inside the backend?

Three reasons, in order of weight:
1. **Embed model lifecycle.** BGE is 1.2GB, ~2-5s cold load. The backend reloads on every code change in dev; the indexer doesn't need to. Uvicorn's reload boundary stops at the indexer.
2. **Vault file-system access.** The backend should never read or write the vault — the operator's source of truth is Obsidian, the indexer is the only system that mutates the cache.db. Cleaner blast radius.
3. **Railway portability.** Railway has no vault. The backend ships there; the indexer doesn't. By making the indexer a sidecar with its own port, the gate is "is it reachable" not "is the model present in this image".

*The downside is one more process to babysit. `run-dev.sh` boots both; production has the indexer as a separate launchd service.*

### Q6.3 Why pre-bake The Street digests instead of computing on every expand?

Because the operator clicks the same row repeatedly, and the underlying data changes weekly at most (snapshot cadence). One Markdown render per ticker per snapshot, cached on disk, serves an arbitrary number of UI expansions for free. The backend lazy-builds when stale (`digests.json` mtime < any source mtime), so a new snapshot drop auto-rebuilds on first access.

*Pre-baking also gives the copy-to-clipboard button something to copy that's already a polished Markdown block, not a JSON envelope the operator has to re-render. The structured per-channel JSON is rendered as React components; the markdown is rendered into the clipboard. Same source.*

### Q6.4 Why extractive teasers (sentence-transformers reuse) instead of LLM summaries?

Latency, cost, determinism. The vault has thousands of chunks; an LLM rewrite per chunk would cost ~$0.30 one-time + cache invalidation discipline + ~1s/chunk first-render latency. The extractive teaser is ~50ms per chunk on the already-loaded BGE encoder, runs synchronously inside `/search`, and never goes stale because it's just a slice of the original chunk. When the operator decides the verbatim-but-shorter version isn't crisp enough, the abstractive layer is a small additive seam: cache `summary_md` per chunk in the indexer's SQLite, fall back to the extractive teaser until generated.

*Tradeoff accepted: long sentences stay long, lists with `1.`/`2.` prefixes parse weirdly. For the 80% case (newsletter prose + book paragraphs) the extractive teaser is readable.*

### Q6.5 Why `min-w-0` everywhere instead of `overflow-x-auto` on parents?

Because the goal is the content reflows into the available width on zoom, not horizontal scroll inside cards. Flex/grid children default to `min-width: auto` which silently overrides `width: 0` and forces them to the intrinsic content size — that's why a long ticker chain breaks the row. Adding `min-w-0` on the right ancestor reverses the default and lets the explicit width win. Combined with `truncate` or `break-words` on the leaf, the row tightens on zoom instead of bleeding past the card.

*The 2026-05-08 layout audit fixed this across Today, Ticker Hub, The Street, and the dashboard tiles. Charts (lightweight-charts) needed a separate fix: `ResizeObserver` on the container instead of `window.resize`, since Cmd+ doesn't always fire `resize` if the window dimensions don't change.*

---

## §7. Expiration triggers — what would force a rewrite

| Trigger | Affected layer | Replacement |
|---|---|---|
| Multi-user requirement | Auth, sync, vault ownership | Per-user namespace + RLS in Postgres; vault becomes shared-via-cloud or per-user |
| Vault > ~100k chunks | Indexer SQLite + vec0 | Postgres + pgvector, OR external vector DB (Qdrant) |
| Multi-model Kronos ensemble | Adapter, queue, accuracy | Adapter accepts `Sequence[Eligible]`; accuracy gains `model_id` axis everywhere |
| Live trading (broker integration) | Trades + opportunities | New `orders` table; idempotency keys; risk gate; reconciliation |
| Real-time tick data | Market data, sync | WebSocket subscription layer; streaming materialised views |
| LLM summary becomes the default | Vault indexer cache.db | New `chunk_summary` table; populate via Haiku batch; serve from cache; extractive becomes fallback |
| Gekko auto-update goes live | Lifespan + scrape pipeline | Playwright job + 13F-HR XML ingest + cron entry; `_source.yaml` flips `enabled: true` |

---

## §8. Paths evaluated but not taken (or parked)

- **Canary-Qwen 2.5B ASR** — top of HF open-ASR leaderboard, English-only. Spike on M3 16GB showed ~5GB model + memory thrash + degenerate output on synthetic TTS. Rolled back fully on 2026-05-06; ~6GB disk reclaimed. Whisper stays default. Tech-debt entry captures the trigger to revisit (32GB+ hardware OR CoreML variant).
- **Per-author vignette landing pages** — discussed but deferred until measured retrieval pain. Operator's vault is small enough that ambiguous attribution hasn't surfaced.
- **Markitdown video-ingest pipeline** — separate workstream; deferred.
- **Gekko auto-update pipeline** — `<vault>/The Street/_source.yaml` captures the contract (sources, cadence, filters) but no code yet. Phase 4 of IA reorg.
- **Abstractive vault summarisation** — Claude Haiku per chunk, cache by `body_hash`. Designed; not built. Extractive teaser is the placeholder.
- **`/v1/tv-context/recent?since=`** — would collapse Today's 8 per-ticker calls into 1. Currently 8 parallel calls; fine while roster stays under 8 tickers, ugly otherwise.
- **Server-side hypothesis-by-ticker filter** — Ticker Hub's HypothesisRow currently filters client-side because `Hypothesis.tickers` is not a first-class column. When the column lands, the filter becomes `?ticker=` on the list endpoint.

---

## §9. Closing — what this architecture optimises for

**One operator, two cadences, three jobs.**

- **Cadences** = morning catch-up (Today) + on-demand decision (Ticker Hub). Everything else is admin or audit, collapsed.
- **Jobs** = (1) detect a signal worth acting on, (2) understand what the system + the vault already know about the underlying, (3) decide and journal the trade with enough context to learn from it later.

The architecture is laptop-primary because compute is on the laptop and Apple Silicon CPU inference is cheap; Railway exists so the operator can read state on the train. The intelligence layer lives next to the prediction layer so the operator never asks "which page" — they ask "which ticker", and the answer is in front of them.

When the system grows past one operator, the trade-offs in §7 force the rewrite. Until then, the design above is deliberately small: one Postgres, one SQLite, one HTTP sidecar, one LLM provider, one auth key, no queue broker, no message bus. Every piece is replaceable and every layer is gitignored or rebuildable.
