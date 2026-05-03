# Architecture review — Data + model decisions

**Date:** 2026-05-02 · **Scope:** Kronos forecasting subsystem + Knowledge Vault + Research stress-test endpoint
**Format:** Q&A. Body answers carry the load-bearing decision; *italicised paragraphs* hold the deeper technical detail you only need when interrogating the choice.

---

## Topology — at a glance

### Kronos (forecasting)

```
                              ┌─────────────────────────────────┐
                              │  HuggingFace Hub (NeoQuasar/*)  │
                              │  Kronos-base 102M / small 24M / │
                              │  mini 4M  +  2 tokenizers       │
                              └────────────┬────────────────────┘
                                           │ snapshot_download (one-time)
                  ┌────────────────────────┴──────────────────────┐
                  ▼                                                ▼
   ┌──────────────────────────┐                    ┌─────────────────────────┐
   │  Laptop (PRIMARY)        │                    │  Railway (REPLICA)      │
   │  HF_HUB_CACHE=./hf-cache │                    │  HF_HUB_CACHE=/data/... │
   │  ~531 MB local, gitignor │                    │  Volume ≥2 GB persisted │
   │  KRONOS_ENABLED=true     │                    │  KRONOS_ENABLED=true    │
   │  uvicorn :8000           │                    │  uvicorn :PORT          │
   │  Postgres :5439 (docker) │                    │  Postgres (Railway)     │
   └────┬─────────────────┬───┘                    └─────┬───────────────┬───┘
        │ submit          │ refresh                     │ submit         │
        │ inference       │ OHLCV (yfinance)            │ inference      │ refresh
        ▼                 ▼                              ▼                ▼
   ┌─────────────────────────┐                    ┌──────────────────────────┐
   │ submit_queue (T1)       │                    │ submit_queue (T1)        │
   │ analysis_jobs / tasks   │                    │ analysis_jobs / tasks    │
   │ prediction_points       │                    │ prediction_points        │
   │ prediction_accuracy     │                    │ prediction_accuracy      │
   │ ohlcv_bars (NOT synced) │                    │ ohlcv_bars (NOT synced)  │
   │ macro_series            │                    │ macro_series             │
   │ sync_outbox ────────────┼──── HTTPS (peer) ─►│ /v1/tickers, /import     │
   │   ticker / result /     │  Tailscale userspc │   (idempotent receivers) │
   │   watchlist / schedule /│  proxy :1055       │                          │
   │   label                 │◄────── HTTPS ──────┤ sync_outbox              │
   └─────────────────────────┘                    └──────────────────────────┘
```

*Lifespan loops in each backend (11 of them): queue worker, accuracy evaluator, drift detector, digest, market-data refresh, opportunities tick, macro ingestion, hypothesis tick, research-weekly, schedule runner, sync-outbox drain.*

### Knowledge Vault + Research

```
   ┌────────────────────────────────────────────┐
   │  ~/Documents/knowledge-vault   (Obsidian)  │   ← canonical, hand-authored
   │  Books/  Newsletters/  Videos/  Notes/     │
   │  _taxonomy.md  _review-queue.md  Research/ │
   │  .indexer/cache.db  (rebuildable, gitignor)│
   └─────────┬──────────────────────────────────┘
             │ FS reads
             ▼
   ┌────────────────────────────────────────────┐         ┌──────────────────┐
   │  vault_indexer SIDECAR (port 8001)         │         │  Anthropic API   │
   │  uvicorn tools.vault_indexer.app:app       │◄───────►│  Haiku 4.5       │
   │                                            │ tags    │  (auto-tag,      │
   │  cache.db: vault_node, vault_chunk,        │         │   ≤15 vocab)     │
   │            vault_chunk_vec  (vec0 1024-d)  │         └──────────────────┘
   │  Embedder: BAAI/bge-large-en-v1.5 (CPU)    │
   │  Endpoints: /search /traverse /node        │
   │             /reload /promote /apply-renames│
   └─────────┬───────────────────────┬──────────┘
             │ HTTP                  │ HTTP-callback (approve/dismiss)
             ▼                       │
   ┌────────────────────────────────────────────┐         ┌──────────────────┐
   │  TradingView FastAPI :8000                 │         │  Anthropic API   │
   │                                            │◄───────►│  Sonnet 4.6      │
   │  app/research/ — bundle, prompt, client,   │  ask    │  prompt-cache:   │
   │   service, routes, weekly                  │         │  ephemeral on    │
   │  Bundle: hypotheses + evidence + macro +   │         │  prefix          │
   │          accuracy snapshot (cap 8k tokens) │         └──────────────────┘
   │  Tool: propose_invalidator_update          │
   │   (3-layer DSL validation gate)            │
   │                                            │
   │  research_queries (audit) + Research/*.md  │
   │   markdown answer (idempotent + frontmatte)│
   │  hypothesis_node_links (vault→hypothesis)  │
   └────────────────────────────────────────────┘
```

*Sidecar runs only on laptop. Railway has no vault, no indexer; Research is a laptop-only feature.*

---

## §1. Kronos — forecasting models

### Q1.1 What model(s) is Kronos and how are they registered?

Three models from **NeoQuasar** on HuggingFace, declared in `app/kronos/registry.yaml`:

| Model | Params | Context | Tokenizer | Use |
|---|---|---|---|---|
| **kronos_base** | 102.3M | 512 bars | `Kronos-Tokenizer-base` | primary |
| kronos_small | 24.7M | 512 bars | `Kronos-Tokenizer-base` (shared) | lighter alt |
| kronos_mini | 4.1M | 2048 bars | `Kronos-Tokenizer-2k` | longest context |

All three carry `unverified: true` until the operator signs off per-model.

*Registry constrains: 6 intervals (`5m, 15m, 30m, 1h, 1d, 1w`), 3 asset classes (`stock, etf, crypto`), required features `[open, high, low, close]` (volume/amount optional). Min history bars + max horizon enforced per-model. `EligibilityValidator.check(...)` is the only gatekeeper — it returns `Eligible` or `Ineligible(reason, message)` and the adapter accepts only `Eligible` instances. No bypass anywhere.*

### Q1.2 Where are the weights stored on each instance?

| | Path | Persistence |
|---|---|---|
| **Laptop** | `./hf-cache/` (gitignored, ~531 MB) | survives uvicorn restarts; manually downloaded once via `snapshot_download` |
| **Railway** | `/data/hf-cache` on a ≥2 GB persisted volume | first inference downloads weights, then survives redeploys indefinitely |

*The volume size matters. HF's snapshot_download writes blob + lock + symlink files; intermediate state briefly doubles footprint. 1 GB is too tight — caused historical OOM. Recommended ≥2 GB. Re-download is only needed when NeoQuasar publishes new weights upstream (hasn't happened in ~6 months).*

### Q1.3 Validator vs adapter — why the split?

`app/kronos/validator.py` is **pure logic, no I/O**. `app/kronos/real_adapter.py` is **lazy-imported heavyweight code** (torch, huggingface_hub, vendored Kronos under `app/kronos/_vendor/`). They're cleanly decoupled because the validator is exercised by every dropdown in the frontend (`/v1/eligibility`, `/v1/timeframes`, `/v1/models`) and every queue submission, while the adapter is only invoked inside the worker loop.

*Choke-point design: adapter takes only `Eligible` instances, never re-validates. Tests can swap a stub adapter via `set_adapter()` without ever booting torch. Phase 3 was able to ship the validator + routing layer before Phase 5 wired the real model.*

### Q1.4 What's the concurrency model for inference?

Single-flight worker. `MAX_CONCURRENT_JOBS=1` on both backends. CPU-only, no GPU. Latency ~15–30 s per `(ticker, interval)` prediction on M3.

*Belt-and-braces: even though the queue worker is single-flight, `app/analysis/concurrency.py::acquire_slot` is still called inside `submit_run`. The queue serialises requests so the slot gate should never fire — it's there as cheap insurance. Logged in `tech_debt.md` with removal trigger "4 weeks zero failures OR Tier-2 queue ships".*

### Q1.5 How is OHLCV fetched, cached, and self-healed?

**Provider**: yfinance only (stock + ETF; crypto provider deferred). Wrapped in `asyncio.to_thread`. **Cache**: `ohlcv_bars(symbol, interval, ts) PK` in Postgres, `ON CONFLICT DO UPDATE`, never expired.

**Self-heal flow** (ADR-010): when accuracy evaluator can't find the actual bar at maturation time, it triggers `md_service.refresh(ticker, interval)` once per `(ticker, interval)` per tick, re-queries cache, evaluates if found. If still missing, upserts `ohlcv_fetch_misses(ticker, interval, target_ts, attempts)` and stops calling provider for that exact tuple after **24 attempts** (one day at hourly cadence).

*Reads stay pure readers — `/predictions/by-horizon`, `/accuracy` never trigger fetches. Background fill is invisible. The 24-attempt cap protects yfinance from being hammered for genuinely unpublishable bars (delistings, holidays, crypto downtime). Lazy refresh also fires inline at end of each analysis task so 1h cadence warms immediately rather than waiting for the next hourly evaluator tick.*

### Q1.6 How are predictions persisted and matured into accuracy?

`prediction_points` is a materialised view of `analysis_tasks.result_json.forecast[]`, exploded by `app/predictions/service.py::explode_task` after each task transitions to `done`. Idempotent via clear-then-insert per task_id (no UNIQUE constraint).

`prediction_accuracy` is per-row error metrics keyed `UNIQUE(prediction_id)`. Hourly lifespan loop (`evaluate_pending`) finds elapsed predictions (`target_ts ≤ now`), joins to `ohlcv_bars` for actual+baseline, computes `error_pct`, `abs_error_pct`, `squared_error`, `direction_correct`, inserts.

*The **rolling aggregation** for the `/accuracy` heatmap reads the **last 30** evaluations per `(ticker, horizon, model, interval)` group — see `app/accuracy/service.py:380-474`. The `+1`/`+2`/`+3` columns are bar offsets, not calendar days; suffix matches interval (1d/1h). Drift detector runs every 6 h, flags pairs whose `recent_mape / all_time_mape ≥ 1.5` after sufficient samples (10 recent, 30 all-time); idempotent on open unacked alerts; posts to Telegram if configured.*

### Q1.7 How do laptop and Railway stay in sync?

**Outbox pattern**, table `sync_outbox(kind, payload_json, attempts, next_retry_at)`. Five kinds: `ticker, result, watchlist, schedule, label`. Exponential backoff `30 s × 2^(attempts-1)` capped at 1 h. Drained by lifespan task + on every job completion + on `POST /v1/sync/retry`.

**Direction-asymmetry**: Laptop → Railway over public HTTPS. Railway → Laptop via **Tailscale userspace networking** with a HTTP CONNECT proxy on `:1055` injected as `HTTP_PROXY`/`HTTPS_PROXY` envs (so httpx auto-routes; no app code changes). `tailscale-entrypoint.sh` brings up `tailscaled` then chains `alembic upgrade head && uvicorn ...`.

*Loop avoidance: imported jobs are tagged `origin='peer'`; the post-job replication hook only fires on `origin='self'`. Watchlist/schedule/label use `apply_imported_*` helpers that bypass the enqueue path entirely. Prevents A→B→A bounce. Receiver-side `POST /v1/analysis/import` is idempotent on `job.id`.*

### Q1.8 What's NOT synced and why?

| Synced | Not synced |
|---|---|
| tickers (catalog) | OHLCV bars (each backend refetches from yfinance) |
| analysis jobs + tasks + forecasts | accuracy evaluations (each backend computes independently) |
| watchlist | drift alerts (per-backend) |
| schedule_config (excluding runtime fields) | opportunities (per-backend) |
| ticker labels | research queries + vault (laptop-only) |

*OHLCV is stateless and yfinance is shared — pointless to sync. Accuracy evaluation is deterministic given the same predictions + bars; each backend lands at the same answer ±a few seconds. Research lives only on laptop because the indexer + vault are laptop-local.*

### Q1.9 What's the queue, scheduler, and daily run pattern?

**Tier-1 queue**: in-process, single-worker, DB-durable. Table `submit_queue(inputs_json, status, source)`. Worker polls every 5 s, wakes immediately on `request_wake()`. Claim via `FOR UPDATE SKIP LOCKED` on Postgres. Crash-recovers stuck `running` rows on boot.

**Schedule**: singleton `schedule_config` row with defaults `enabled=False, run_at_local=23:30 UTC, intervals=[1d], horizon_bars=5, model_ids=[kronos_base], skip_weekends=True, collect_actuals=True`. Runner ticks, computes `is_due`, enqueues if so, then collects actuals + evaluates pending accuracy after success.

*Mid-tick PUT race (ADR-011) was a real bug: `record_run` is the only writer of `next_run_at` at tick boundaries, reloads config inside its own session, calls `compute_next_run_at(cfg, now=advance_now)` so a `PUT /v1/schedule` landing while `_tick` mid-execution doesn't lose the write. Catch-up path: first iteration computes `next_run_at` if missing; if already past (laptop was off), fires immediately on startup.*

**Railway-fallback inference** (opt-in): Railway runs the day's predictions itself if the laptop missed its window by `fallback_offset_hours` (default 6 h). Off by default — flip `RAILWAY_FALLBACK_ENABLED=true` on the Railway service to engage. Per-day dedupe is best-effort.

### Q1.10 Where would the Kronos design break?

| Trigger | What expires |
|---|---|
| Sustained queue depth > 5 OR GPU lands OR CPU < 3 s/run | Tier-1 queue → Tier-2 (Redis + arq), separate worker process |
| 4 weeks of zero `acquire_slot` failures OR Tier-2 ships | Concurrency slot gate removed |
| Watchlist > ~200 symbols | yfinance rate-limit risk → add jitter / global concurrency cap on `md_service.refresh` |
| Row count > 1M per table | Reassess Postgres-only durability; selective Redis caches |
| Next `schedule_config` schema change | Drop unused `pending_run`, `retry_minutes`, `last_run_status='deferred_429'` columns |
| Crypto/options become first-class | New provider implementation; `Provider` protocol already supports it |
| NeoQuasar publishes new weights | One-shot snapshot_download + tag bump in registry.yaml |

---

## §2. Knowledge Vault — corpus + indexer + research

### Q2.1 What is the vault and where does it live?

`~/Documents/knowledge-vault` — operator's Obsidian vault. **Markdown files are canonical**; everything else (cache, embeddings, suggestions) is rebuildable.

```
Books/                  # Class A (timeless, decay = 1.0)
Newsletters/<author>/   # Class B (decay-weighted, default horizon 6mo)
Videos/<author>/        # Class B
Notes/                  # Class A
Topics/                 # Class A (optional landing pages per tag)
_taxonomy.md            # 15-tag controlled vocabulary
_review-queue.md        # tag suggestions awaiting tick
Research/               # Phase 3 stress-test answers
.indexer/cache.db       # SQLite + sqlite-vec, gitignored, rebuilds <10 min
```

*Frontmatter schema (`kind, title, author, source_url, source_path, source_sha256, published_at, ingested_at, horizon_months, parent, tags`). PDFs/EPUBs ingested via layout-aware splitter (`tools/vault_indexer/ingest/pdf_layout.py`) that detects chapters before chunking. Auto-flags `chapter_has_figures/tables/landscape` so operator can later filter on image presence (precursor to the vision-retrieval backlog item).*

### Q2.2 What is the indexer sidecar and why is it a separate service?

FastAPI app on **port 8001**, run with `uvicorn tools.vault_indexer.app:app --port 8001`. Eight endpoints: `/health, /reload, /node/{path}, /search, /traverse, /promote, /apply-renames, /regenerate-review`.

*Three reasons to be a sidecar (ADR-014:144-151): (1) vault is canonical and indexer cache is rebuildable, so it's safe to restart indexer without touching the main app; (2) decouples heavy deps (sentence_transformers, apsw, sqlite_vec) from the FastAPI app's import graph; (3) future second consumer (n8n, scripts, another tool) can read the same vault. Reversibility is cheap — extraction to a separate repo is `git mv` + tag.*

### Q2.3 Why SQLite + sqlite-vec instead of Postgres + pgvector?

Two reasons. **Practical**: Docker Postgres image used for laptop dev doesn't ship pgvector — `CREATE EXTENSION vector` failed and the install path was non-trivial. **Architectural**: ~13k chunks today (~8M tokens at 600 tokens/chunk) is tiny — sqlite-vec is overspec'd for the volume. A single file decouples the cache from TradingView's Postgres entirely.

*Apsw (not stdlib sqlite3) is required because Apple's Python disables loadable extensions, and sqlite-vec is loaded as one. Embedding cost is ~zero at operator volume (1–5 notes/week ingested). Reversibility: extract to Postgres + pgvector when a second consumer materialises that wants the data.*

### Q2.4 What embedding model and why?

**`BAAI/bge-large-en-v1.5`** — 1024-dim, cosine-native, English-only, MIT-licensed, ~1.3 GB on disk (HF cache shared with Kronos torch cache).

| Why this model | Alternative considered |
|---|---|
| MTEB ~64 vs MiniLM-L6-v2 ~42 — 20 pp recall gap matters at curator scale | MiniLM is faster + smaller but loses too much |
| Cosine-native, fits sqlite-vec KNN cleanly | OpenAI text-embedding-3-large (paid, network call per chunk) |
| English-only is fine — operator reads English | bge-m3-large (multilingual; not needed today) |
| CPU-friendly inference; throughput non-constraint | Gemini multimodal embeddings (parked as backlog item) |

*bge guidance recommends a query-side prefix `"Represent this sentence for searching relevant passages: "` to align query embeddings with passage embeddings; passages are encoded raw. Distance metric is cosine; converted to similarity ∈ [-1, 1] at retrieval. Default top-K = 12, exposed up to 50.*

### Q2.5 How is the cache structured and persisted?

```sql
vault_node(path PK, kind, title, author, published_at, ingested_at,
           horizon_months, parent_path, tags[], body_hash, body_md, last_indexed_at)
vault_chunk(id PK, path FK, ord INT, text, section)
vault_chunk_vec USING vec0(chunk_id, embedding FLOAT[1024])
vault_edge(src_path, dst_path, kind, weight)  -- explicit + computed
```

Embeddings keyed on `body_hash`, so file content unchanged → no re-embed. Laptop reboot → no re-embed. **Full rebuild is < 10 min**.

*Chunking targets ~600 tokens with 80-token overlap (`CHUNK_TARGET_TOKENS / CHUNK_OVERLAP_TOKENS`). For PDFs/EPUBs, layout-aware splitter respects chapter boundaries; for plain markdown, semantic splitting by sentence + token target.*

### Q2.6 How are tags managed?

**15-tag controlled vocabulary** maintained by the operator in `<vault>/_taxonomy.md`. Auto-suggest by Claude Haiku 4.5 — suggestions land in `_review-queue.md` as checkboxes; **the indexer never writes a tag the operator didn't tick**. Auto-tag is off when `ANTHROPIC_API_KEY` is unset.

*Why a fixed vocabulary: free-form tags fragment too fast (`liquidity` vs `Liquidity` vs `Liquidity-trap`); a hand-editable file is more ergonomic than CRUD endpoints. Why Haiku: ~$0.0002/note; ~$0.30/year at 1–5 notes/week. The "operator-in-the-loop review queue is plain markdown checkboxes" pattern is **the cheapest possible operator-in-the-loop**. No new UI, full audit trail in git.*

### Q2.7 How does Research bundle evidence + macro + accuracy?

Per `app/research/bundle.py`, every `/v1/research/ask` builds a JSON bundle with:

1. **Hypothesis cards** (per slug or every active row): slug, title, claim_type, axis, status, expires_at, primary_metric, tracking_signal, current `invalidator` JSON, last 3 `hypothesis_evaluation` rows, `linked_vault_paths` from `hypothesis_node_links`.
2. **Evidence**: `GET http://localhost:8001/search?q=&k=` against the indexer. Preference order: linked_vault_paths first (filtered top-K), generic search if linked-only starves the result.
3. **Macro snapshot**: latest value for each `tracking_signal` + any symbol named in `invalidator.args`.
4. **Accuracy snapshot**: 14-day hit-rate + MAPE for tickers in the bundle (best-effort; missing module is no-op).

**Hard cap 8000 tokens** (`HARD_TOKEN_CAP`). Truncation order: oldest evaluations → lowest-score excerpts → trim longest excerpt body.

*If indexer is down, bundle still assembles with empty `evidence[]`; the route doesn't fail. Phase 3.7 flattened evidence + macro_state into the API response itself so the frontend can render without a second call.*

### Q2.8 What's the prompt + tool-use pattern?

System prompt frames the operator as a **single trusted user**, the platform as **never trading directly**, and the answer shape as a **suggestion for human review**. Hard rules: never invent evidence, only cite bundled paths; never output trade advice; never hedge; be concrete.

**Single tool: `propose_invalidator_update`** with input schema mapping directly onto the 5-op DSL (`ratio_below_sma, series_above_threshold, series_below_threshold, series_change_pct, manual`).

**Three-layer DSL validation gate** runs server-side before the markdown is written:
1. `inv_dsl.validate_spec(proposed_invalidator)` — DSL well-formed
2. `hypothesis_slug` ∈ bundle's hypothesis list (no proposing for theses Claude wasn't shown)
3. `evidence_paths` ⊆ bundle's evidence list (no citing hallucinated content)

Failure drops the action; the markdown gets a verdict-only "no concrete change" answer instead. The approve route **re-validates the DSL** before patching the hypothesis row (defense in depth).

*Prompt-cache: system prompt + bundle-prefix carry `cache_control: {type: "ephemeral"}` so repeat queries on the same hypothesis pay the cache-read rate ($0.30/Mtok) on the prefix instead of full input ($3.00/Mtok). Roughly 20–30% of first-query cost.*

### Q2.9 How does approval work end-to-end?

Markdown answer is written to `<vault>/Research/{date}-{slug}.md` with frontmatter (`kind, hypothesis_slug, asked_at, research_query_id, tags`). Body has Query → Verdict → Evidence wikilinks → Macro state → Proposed action with `**Approve:** [ ]` and `**Dismiss:** [ ]` checkboxes → cost line.

Operator ticks `[x]` and saves. The indexer's `POST /promote` regex-detects ticked Approve/Dismiss lines, reads `research_query_id` from frontmatter, and HTTP-calls the laptop's `/v1/research/queries/{id}/approve|dismiss`. The route patches `hypothesis.invalidator` after re-validating. Indexer stamps `<!-- vault-indexer:applied -->` so subsequent passes skip the file.

*Phase 3.7 added a React UI on top — same backend, button-based approve goes through a confirm modal that shows current vs proposed JSON. Markdown files **keep getting written for archival + weekly auto-stress** even when approve happens via UI. Phase 3.7's DELETE route hard-deletes the `research_queries` row but **does NOT remove the markdown archive** from the vault — the operator owns vault cleanup separately.*

### Q2.10 What's the auto-stress weekly task?

Lifespan task `research-weekly` in `app/main.py`. Sleeps `RESEARCH_WEEKLY_WARMUP_SECONDS` after boot (default 1 h), then fires `run_once()` every `RESEARCH_WEEKLY_SLEEP_SECONDS` (default 7 days).

`run_once`: for each active hypothesis, call `service.ask(query=DEFAULT_COUNTERARG_QUERY, hypothesis_slugs=[slug])`, append a one-liner summary to `<vault>/_review-queue.md`. Per-hypothesis failure logs and skips, doesn't break others.

*With 6 active hypotheses: 6 × ~$0.025 = ~$0.15/week → ~$8/year baseline cost. Operator-initiated queries add similar marginal cost. No daily token budget — solo-operator volume doesn't justify the guard. If usage scales, add one.*

### Q2.11 Where would the Vault/Research design break?

| Trigger | What expires |
|---|---|
| Operator runs ≥3 queries / same hypothesis / 7 days AND wants context across answers | Phase 3.8 threading promotes from direction notes to executable plan |
| Free-form tags consistently exceed 15 (the controlled vocabulary) | Backlog: entity-extraction-into-frontmatter (LightRAG-lite) |
| Operator hits 3+ "I wanted to read the chart/equation/table visually" moments / 2 weeks | Backlog: vision-retrieval (Gemini multimodal embeddings) |
| Vault > ~100 k chunks OR cache.db > 5 GB OR rebuild > 15 min OR query latency > 2 s | Reassess sqlite-vec → Postgres + pgvector |
| Operator ingests non-English content | Swap to multilingual embedder (e.g. `bge-m3-large`) |
| BAAI publishes v2 with ≥5 pp MTEB lift | Re-embed vault (backwards-compatible if same dim) |
| Operator complains "bundle keeps truncating critical evidence" | Compression strategy + bigger token cap |
| Anthropic input price shifts materially | Override env vars; or Phase 3.5 multi-LLM cross-check (parked) |
| Auto-stress files go unread for 2–3 weeks | Phase 3.3 Telegram digest of unread answers (parked) |

---

## §3. Cross-cutting trade-offs

### Q3.1 What's "operator-as-curator" and where does it show up?

Load-bearing principle from `principles.md`. Concretely:

- Hypotheses are **hand-authored**; Claude can only propose invalidator tightenings, never new theses.
- Tags are **operator-tickable**; Haiku suggests, never auto-applies.
- Approval flow is **markdown-first**; the canonical artifact is a versioned file.
- Research answers are **archived in the vault**; the UI is a complement, not a replacement.
- Drift alerts, opportunities, predictions are **read-only signals** for the operator — the platform never trades.

*The principle is what enables many cost-saving choices: no auth tiers, no multi-tenancy, no soft-delete, no audit log beyond Postgres rows + git history, no per-user state. It also bounds expressivity — open-ended chat against the corpus is **out of scope** (operator uses Claude API directly when they want it). This is a strategic, not technical, line.*

### Q3.2 What's "single user" cost-saving and where does it show?

Every layer:

| Layer | Single-user concession |
|---|---|
| Auth | One API key, no roles, no per-user state |
| Sync | Outbox best-effort, exponential backoff, no exactly-once semantics |
| Workers | 11 lifespan loops in one process, no celery/arq |
| Queue | Tier-1 single-flight worker, ~1 job/day baseline |
| Cache | sqlite-vec on a single file, no replication |
| Telegram | Optional, no-op when unconfigured |
| OHLCV | Stateless yfinance refetch, no replication |
| Research | Vault on laptop only; no Railway parity |
| Schedule | Singleton config row, last-write-wins |

*If "single user" stops being true — say, second operator joins, or a contractor needs read access — most of these need rework. Estimated cost: 2–4 weeks of careful refactor across auth + roles + per-user state + sync semantics. Until that day, every concession is a win.*

### Q3.3 What's "cheap reversibility" and how does it constrain decisions?

From `principles.md` + roadmap-shipped Phase 0: every phase is **tagged in git** (e.g. `v1.0-pre-trust-sprint`), DB dumps taken before destructive change, `backups/ROLLBACK.md` documents the back-out. Phase 0 alone added ~30 min/phase overhead in exchange for "back out" door that always works.

*Impact on architecture: the queue + concurrency gate co-exist (belt-and-braces) because each is independently reversible. The vault sidecar is decoupled because it's `git mv`-able. Migration 0019 (`macro_series`) was kept separate from `ohlcv_bars` despite both being time-series, because the abstraction cost was higher than the reversal cost. The general pattern: **prefer copies + later consolidation over premature unification.***

### Q3.4 Where did we explicitly accept lower performance for higher fit?

Examples:

1. **CPU-only Kronos inference** — ~15–30 s vs sub-second on a GPU. Fit: solo-operator pace + no GPU on laptop or Railway free tier.
2. **sqlite-vec over pgvector** — slightly slower at scale. Fit: 13 k chunks + single consumer + sidecar simplicity.
3. **Hourly accuracy evaluator** — could run continuously. Fit: matches the daily prediction cadence; bars don't change minute-to-minute.
4. **Tier-1 queue** — no parallelism, no priorities, no DLQ. Fit: 1 job/day baseline, GPU-less.
5. **Outbox best-effort** — no exactly-once. Fit: idempotent receivers + operator can manually retry.
6. **Markdown-first approval** — slower than button-click. Fit: inspectable artifact + matches operator's reading habits.

### Q3.5 Where did we get higher fit at lower cost?

1. **Postgres for everything** — durability, ACID, mature tooling, single backup target. Avoids Redis/Mongo/etc.
2. **In-process workers** — easy to reason about, deploy, and debug. Avoids worker-process orchestration.
3. **Phase-tagged git** — rollback is `git reset --hard <tag>` + DB restore. Avoids feature flags + dark launches.
4. **Plain markdown checkboxes for review** — zero new UI for tag review + research approval. Avoids a CRUD admin page.
5. **15-tag controlled vocabulary** — Hand-editable file beats a tag-management UI for a single user.
6. **Prompt-cache on bundle prefix** — 5x cost reduction on repeat queries with zero code complexity beyond `cache_control: ephemeral`.

### Q3.6 What's load-bearing about projected volumes?

| Volume assumption | Where it gates a design choice |
|---|---|
| ~1 analysis job/day | Tier-1 queue is single-flight |
| ~1–5 notes/week ingested | sentence_transformers CPU is plenty |
| ~6 active hypotheses | Bundle fits in 8 k tokens |
| ~5 research queries/week | No daily token budget needed |
| Watchlist ≤ ~50 tickers | yfinance refresh isn't rate-limited |
| Macro = 38 symbols, daily | Single chunked upsert per tick |
| Vault < 100 k chunks | sqlite-vec + bge-large is overspec'd |
| Single laptop + single Railway instance | Outbox + Tailscale topology trivially fits |

*Most of these have at least 10× headroom before they break. The first to break is probably **watchlist size** (yfinance rate limits on burst), followed by **cache.db rebuild time** if the operator front-loads a large book ingest.*

---

## §4. Expiration triggers — consolidated

The single-table view of "what to watch for; what to do when":

| # | Signal | Trigger | What to do |
|---|---|---|---|
| 1 | Queue depth > 5 sustained | 4 weeks | Tier-2 queue (Redis + arq) + separate worker process |
| 2 | GPU lands on laptop or Railway | one-shot | Tier-2 queue + multi-worker; `MAX_CONCURRENT_JOBS > 1` |
| 3 | Kronos-base CPU < 3 s/run | one-shot | Tier-2 queue worth the infra |
| 4 | Zero `acquire_slot` failures | 4 weeks | Drop concurrency slot gate |
| 5 | Next `schedule_config` schema change | one-shot | Drop unused `pending_run`, `retry_minutes` columns |
| 6 | Watchlist > 200 symbols | one-shot | Add jitter / global concurrency on `md_service.refresh` |
| 7 | Row count > 1M per any table | one-shot | Reassess Postgres-only durability; selective Redis |
| 8 | Operator runs ≥3 queries / same hypothesis / 7 days | one-shot | Phase 3.8 threading promoted to plan |
| 9 | Free-form tag fragmentation > 15 | drift signal | Entity-extraction-into-frontmatter (backlog) |
| 10 | "Wanted to read chart/table" 3+ times / 2 weeks | drift signal | Vision-retrieval (Gemini multimodal embeddings) |
| 11 | Vault > 100 k chunks OR cache.db > 5 GB | one-shot | Postgres + pgvector for vector store |
| 12 | Operator ingests non-English | one-shot | Multilingual embedder (`bge-m3-large`) |
| 13 | BAAI v2 with ≥5 pp MTEB lift | one-shot | Re-embed vault |
| 14 | Auto-stress files unread 2–3 weeks | drift signal | Phase 3.3 Telegram digest |
| 15 | Bundle keeps truncating critical evidence | drift signal | Compression strategy + bigger cap |
| 16 | NeoQuasar publishes new Kronos weights | one-shot | snapshot_download + registry.yaml bump |
| 17 | Single-user assumption breaks | one-shot | 2–4 weeks of auth/roles/per-user-state refactor |
| 18 | sentence_transformers tests broken (today, 2026-05-02) | known | Pin `transformers<5` OR bump `huggingface_hub`; tech_debt entry |

---

## §5. Paths evaluated but not taken / parked

```
       SHIPPED (operator-as-curator, single-user, markdown-first)
   ┌──────────────────────────────────────────────────────────┐
   │  Kronos: validator + adapter + Tier-1 queue + outbox     │
   │  Vault: sidecar + sqlite-vec + bge-large + Haiku auto-tag│
   │  Research: Sonnet ask + 3-layer DSL gate + md approval   │
   │  Phase 3.7: React UI with confirm-modal + accordion      │
   └──────┬───────────────────────────────────────────────────┘
          │
          ├──► PARKED — operator unlocks
          │    ├─ Telegram bot setup (5 min, gated on operator)
          │    ├─ Streaming research responses (Phase 3.6)
          │    ├─ Phase 3.8 threading (gated on 3+/7d signal)
          │    ├─ Phase 3.3 Telegram digest of unread answers
          │    ├─ Phase 3.4 Cross-hypothesis stress
          │    └─ Phase 3.5 Multi-LLM cross-check (Claude + GPT)
          │
          ├──► PARKED — scale unlocks
          │    ├─ Tier-2 queue (Redis + arq + multi-worker)
          │    ├─ Postgres + pgvector (when vault > 100k chunks)
          │    ├─ Concurrency-gate removal (4 weeks zero failures)
          │    └─ Schedule_config column drop
          │
          ├──► PARKED — corpus unlocks
          │    ├─ Entity-extraction (LightRAG-lite) when 15-tag drifts
          │    ├─ Vision-retrieval (Gemini multimodal)
          │    ├─ 13F + Form-4 ingestion (M-5)
          │    └─ Hypothesis backtest engine (M-6)
          │
          └──► OUT OF SCOPE — strategic
               ├─ Multi-tenancy / auth roles
               ├─ News/policy/commentary ingestion (operator owns externally)
               ├─ Brokerage API integration (manual journaling acceptable)
               ├─ Mobile-first responsive layout (Telegram serves mobile)
               ├─ Free-form open chat over corpus (use Claude API directly)
               └─ Multi-hypothesis threads (sign that question shape is wrong)
```

*"Out of scope — strategic" is the load-bearing list. These are not "we'll get to it later" — they're "if we built this, the system would no longer match its founding principle." Reverting any one of them implies a wholesale re-think.*

---

## §6. Closing — what this architecture optimises for

It optimises for **one operator, slow cadence, deliberate decisions, cheap reversibility**. Every choice is downstream of that. The result:

- **Pennies/month** in API costs.
- **<10 min** rebuild time for the entire knowledge index.
- **<2 weeks** to replace any single component with no in-flight migrations.
- **0 lost work** in any documented failure mode (every phase tagged + dump-snapshotted).
- **3-8 s** end-to-end latency on a stress-test query.
- **1 process** per backend, **1 worker** per process, **1 vault** per operator.

The cost is that **none of it scales horizontally**. Multi-user, multi-vault, real-time trading, GPU inference — all cross the line into a different system. The signals that would force the crossing are listed in §4. Until one of them fires, the design is right-sized.

---

*Source files referenced in this review:*
*`CLAUDE.md`, `.claude/principles.md`, `.claude/architecture.md`, `.claude/kronos.md`, `.claude/market_data.md`, `.claude/sync.md`, `.claude/laptop-setup.md`, `.claude/railway-deployment.md`, `.claude/queue.md`, `.claude/schedule.md`, `.claude/predictions.md`, `.claude/accuracy.md`, `.claude/macro.md`, `.claude/vault.md`, `.claude/research.md`, `.claude/hypotheses.md`, `.claude/glossary.md`, `.claude/recipes.md`, `.claude/backlog.md`, `.claude/tech_debt.md`, `.claude/roadmap-shipped.md`, `.claude/decisions/{010,011,012,013,014,015}.md`, `.claude/plans/phase-3-stress-test.md`, `.claude/plans/phase-3.7-research-ui-single-turn.md`, `.claude/plans/phase-3.8-research-ui-threading.md`. Code under `app/kronos/`, `app/market_data/`, `app/macro/`, `app/sync/`, `app/queue/`, `app/schedule/`, `app/predictions/`, `app/accuracy/`, `app/research/`, `app/hypotheses/`, `tools/vault_indexer/`. Migrations 0008, 0010–0013, 0015–0019, 0021–0023.*
