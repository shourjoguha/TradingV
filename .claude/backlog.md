# Backlog

Deferred decisions and known-but-unaddressed gaps. Each entry: what, why deferred, options considered, current state, trigger to revisit.

> **Tech debt** (cruft we knowingly left in shipped code) lives separately at [.claude/tech_debt.md](tech_debt.md). Backlog is for *features*; tech_debt is for *code chores*.

---

## Decision-tool roadmap — see [.claude/roadmap.md](roadmap.md)

**Status (2026-04-30):** Phases 0-6 SHIPPED. All backend tables + lifespan loops + endpoints + frontend pages live. 269 tests pass. Unlock #2 RESOLVED via self-healing OHLCV fetch (ADR-010); scheduler mid-tick PUT race RESOLVED (ADR-011); **Macro Workbench M-1 (signal layer) shipped** ([macro.md](macro.md), [decisions/012](decisions/012-macro-workbench-storage-shape.md)) — `/v1/macro/{series,ratio,refresh}` live with 38 symbols ingesting daily. Telegram still dormant — see Unlock #1. Next: Macro Workbench M-2 (hypothesis object + view registry) — see [plans/M-2-hypothesis-object.md](plans/M-2-hypothesis-object.md).

| Phase | Title | Status |
|---|---|---|
| 0 | Snapshot (rollback safety) | ✅ tag `v1.0-pre-trust-sprint` |
| 1.1 | prediction_accuracy + evaluator | ✅ live |
| 1.2 | /accuracy frontend | ✅ live |
| 1.3 | drift detection + Telegram alerts (backend) | ✅ live (Telegram dormant — see unlock #1) |
| 2.1 | empty states | ✅ live |
| 2.2 | lightweight-charts v5 upgrade | DEFERRED — not on critical path |
| 3.1 | opportunities + signal generator | ✅ live (self-healing OHLCV — see unlock #2 RESOLVED) |
| 3.2 | /opportunities frontend | ✅ live |
| 4 | daily Telegram digest | ✅ live (dormant until Telegram set up) |
| 5 | trade journal (backend + frontend) | ✅ live |
| 6 | options runway data layer | ✅ live (silently collecting IV + earnings daily) |

Roadmap doc has locked decisions (metrics, drift threshold, channel, sequencing). Update there, not here.

---

## Re-evaluate active hypotheses every 12 months

**What:** Each hypothesis under [`.claude/hypotheses/draft/`](hypotheses/draft/) (and later under the M-2 DB-backed object) carries a `ttl_months` value. Long-horizon ones (24-36mo regime / breakout theses) deserve a **mid-life review** at the 12-month mark even when none of the named invalidators have fired. Markets reorganise around new macro narratives faster than thesis-text can adapt; a 12-month checkpoint is the discipline lever that keeps the workbench from becoming "always-bullish-on-X" decoration.

**Trigger / cadence:** Every 12 months from `created_at`, or sooner if any cross-hypothesis development warrants it (e.g. precondition cascade, regime shift on the dedicated panel). When M-2 ships, this lives as a `next_review_at` field on the hypothesis row and a banner on the `/macro` page.

**Process when a review fires:**
1. Re-read the hypothesis text against the current `tracking_signal` and `ratios` data — does the *thesis* still describe what's happening?
2. Confirm the four invalidator categories are still the right ones. If you'd word them differently today, update them.
3. Check confirming-evidence section for staleness ("multi-decade trendline broken" was true 12 months ago — is it still?).
4. Decide: keep, modify, or cancel-and-replace.

**Active hypotheses to re-review:**
- `latam-breakout-36m.md` — review by 2027-04-30
- `latam-breakout-18m.md` — review by 2027-04-30 (or earlier — it's the tactical confirmation)
- `saas-mission-critical-2x-18m.md` — review by 2027-04-30
- `btc-bottom-3m.md` — short TTL, doesn't need a 12mo review (it'll resolve sooner)
- `btc-rally-24m.md` — review by 2027-04-30
- `stagflation-regime-24m.md` — review by 2027-05-01

**Trigger to revisit (this backlog item):** automatic — schedule a one-time agent for 2027-04-30 once M-2's `next_review_at` is in the schema. Until then, manual review.

---

## Unlock #1 — Telegram bot setup (~5 min) — DEFERRED

**What:** Drift alerts + daily digest are coded + live but no-op until `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars are set on Railway (and optionally laptop). Notifier logs once at startup that it's not configured, then stays silent. Code is deploy-safe in this state.

**Steps when revisiting:**
1. On Telegram, DM @BotFather → `/newbot` → follow prompts → save the token (looks like `123456:ABC-DEF...`).
2. DM your new bot any message (forces a chat to exist).
3. `curl https://api.telegram.org/bot<TOKEN>/getUpdates` → in the JSON response, copy `result[0].message.chat.id` (an integer).
4. Railway dashboard → service → Variables → add:
   - `TELEGRAM_BOT_TOKEN=<token>`
   - `TELEGRAM_CHAT_ID=<chat_id>`
5. Save → Railway redeploys → drift alerts post on next detection tick (every 6h); daily digest fires at `DIGEST_HOUR_UTC` (default 12 = 8 AM ET).
6. Test: `curl -X POST -H "X-API-Key: <RAILWAY_KEY>" https://tradingv-production.up.railway.app/v1/accuracy/drift/detect` — if any drift exists you'll get the message instantly.

**Files involved:** `app/notifications/telegram.py`, `app/notifications/digest.py`, `app/accuracy/drift.py`, `app/core/config.py`.

**Trigger to revisit:** when you want push notifications instead of polling the dashboard.

---

## Unlock #2 — Self-healing OHLCV fetch  ✅ RESOLVED

**Resolution (2026-04-30):** Option A landed. Accuracy evaluator's hourly tick now calls `md_service.refresh()` when a pending prediction's actual is missing — deduped per `(ticker, interval)` per tick, capped per `(ticker, interval, target_ts)` lifetime via `ohlcv_fetch_misses` (max 24 attempts ≈ one day at hourly cadence). Same lazy refresh added to the analysis pipeline (`_process_task`) so cold-start intervals like 1h get warmed automatically. See [decisions/010](decisions/010-self-healing-ohlcv-fetch.md).

Baseline (`made_on` close) for opportunities is still cache-only today; same approach can extend there if needed (low priority — usually present once analysis lazy-refresh ran).

**Files:** `app/accuracy/service.py::evaluate_pending` + `_try_refresh_actual`, `app/accuracy/models.py::OhlcvFetchMiss`, `migrations/versions/0018_ohlcv_fetch_misses.py`, `app/analysis/service.py::_process_task`.

---

---

## Charting library — lightweight-charts v5 chosen over Plotly (deliberation)

**Decision (2026-04-27):** Stay on lightweight-charts; upgrade v4 → v5 in Phase 2.2. Plotly evaluated and rejected for primary OHLC charting.

Reasons:
- lightweight-charts is TradingView's own lib, purpose-built for OHLC + overlays. v5 added crosshair sync, drawing tools, multi-pane.
- ~50 KB vs Plotly ~3 MB gzipped. Bundle bloat unacceptable for a single-user tool that doesn't need scientific viz.
- Plotly reserved for the future options chapter (vol surfaces, Greeks plots, 3D) — different problem.

Trigger to revisit: building options strategy generator or wanting non-OHLC scientific overlays.

---

## Cloud frontend hosting (Lovable rejected → Cloudflare Pages)  ✅ RESOLVED

**Resolution (2026-04-27):** Lovable evaluated, rejected — no existing-repo import, no build-time `VITE_*` env var UI, no per-PR preview URLs, no header/redirect config, AI editor mutates source. Switched to **Cloudflare Pages** at `https://tradingv-83b.pages.dev`. Plan: `/Users/shourjosmac/.claude/plans/cloudflare-pages-port.md`. New artifacts: `frontend/public/_redirects` (SPA fallback) + CF dashboard config + Railway `FRONTEND_ORIGIN`. No `frontend/src/` changes.

---

## Reverse-direction sync: Railway → Laptop  ✅ RESOLVED

**Resolution:** Phase B1+B2 of backlog rollout. Tailscale chosen (Option A from the original three).

How it works in production:
- `Dockerfile` installs Tailscale; `tailscale-entrypoint.sh` runs `tailscaled --tun=userspace-networking --outbound-http-proxy-listen=:1055`, then `tailscale up` joins the operator's tailnet as ephemeral host `tradingv-railway-N`.
- Container exports `HTTP_PROXY=http://127.0.0.1:1055` + `HTTPS_PROXY=http://127.0.0.1:1055` + `NO_PROXY=localhost,127.0.0.1,postgres.railway.internal,.railway.internal,.railway.app`. httpx + urllib + requests auto-route through tailscaled.
- `PEER_API_URL=http://<laptop-tailnet-ip>:8000` (note port — see lessons below).
- `PEER_API_KEY=<laptop's API_KEY>`.

Verified: Railway-originated job pushes both `kind='ticker'` and `kind='result'` outbox rows; laptop receives the imported job (origin='peer'), explodes prediction_points; comparison endpoints on laptop see the data.

**Lessons learned during rollout** (worth a re-read if anyone touches the tunnel):
1. `[deploy].startCommand` in `railway.toml` BYPASSES the Docker ENTRYPOINT — the entrypoint script never ran. Removed startCommand to let ENTRYPOINT chain into CMD.
2. `tailscaled --tun=userspace-networking` does NOT install kernel routes — direct connection to `100.x.y.z` hangs. Must use the HTTP proxy.
3. `ALL_PROXY=socks5://...` makes httpx import `socksio` (not in requirements). Don't set ALL_PROXY; HTTP_PROXY/HTTPS_PROXY cover both protocols.
4. `PEER_API_URL` MUST include the port (`:8000`); without it requests go to port 80 and 502 from the proxy.

---

## sync_outbox cleanup task  ✅ RESOLVED

**Resolution:** Phase C1. `purge_loop()` lifespan task ticks hourly, deletes rows where `completed_at < now() - OUTBOX_RETENTION_DAYS` (default 7). Pending rows are never touched. Tested in `tests/test_outbox_cleanup.py`.

---

## asset_class reconciliation  ✅ RESOLVED

**Resolution:** Phase C3. `tickers_svc.upsert_ticker` enqueues a `kind='ticker'` sync row when asset_class transitions from `unknown` (or empty) to a real class. Same code path as the existing ticker push — receiver upserts via `POST /v1/tickers`. Tested in `tests/test_sync.py`.

---

---

## Railway-fallback inference when laptop down  ✅ RESOLVED

**Resolution:** Phase B4. Lifespan task `_fallback_loop()` in `app/schedule/runner.py` ticks every 30 min on Railway when `RAILWAY_FALLBACK_ENABLED=true`. Per-symbol dedupe via `prediction_points`. Configurable `fallback_offset_hours` on `schedule_config` (default 6h). Tested in `tests/test_schedule_fallback.py`.

---

## Watchlist + schedule_config + labels replication to Railway  ✅ RESOLVED

**Resolution:** Phase B3. `sync_outbox.kind` extended with `'watchlist' | 'schedule' | 'label'`. Each external CRUD on watchlist / schedule / label enqueues a row; drain dispatches to peer `POST /v1/{watchlist,schedule,labels}/import`. Receivers bypass the enqueue path so imports don't loop. Tested in `tests/test_sync_replication.py`.

---

## Job submission queue (replace 5-min poll + eliminate 429s)  ✅ RESOLVED

**Resolution (2026-04-27):** Tier-1 in-process queue shipped — see [.claude/queue.md](queue.md). `submit_queue` table (migration 0017) + single-flight `worker.worker_loop` lifespan task. `POST /v1/analysis/run` returns 202 with `queue_id`; schedule runner enqueues like any other caller. Crash recovery via `reset_stuck_on_boot()`. Cancellation supported on `pending` items only. Frontend: toast on submit, queue widget on Dashboard, queue card with cancel buttons on AnalysisJobs page. 245 tests pass.

**Tier 2 (Redis + arq workers)** deferred — see [.claude/tech_debt.md](tech_debt.md). Trigger to revisit: sustained queue depth > 5 OR GPU inference lands.

---

## Trading-day filter per asset_class  ✅ RESOLVED

**Resolution:** Phase C2. `app/market_data/calendar.py::is_trading_day(asset_class, date)`: stocks/ETFs/forex/futures = Mon-Fri; crypto/commodity = always; unknown = always (permissive fallback). Scheduler partitions watchlist by asset class on each tick. Tested in `tests/test_calendar.py`.

---

## CORS middleware for browser-side Railway toggle  ✅ RESOLVED

**Resolution:** `CORSMiddleware` wired in `app/main.py`. Allow-list driven by `FRONTEND_ORIGIN` env var (CSV of absolute origins). When unset, falls back to `http://localhost:{3000,5173}` so local dev works out of the box. Set `FRONTEND_ORIGIN=https://<your-app>.lovable.dev` on Railway when frontend deploys.

---

## Scheduler loses today's slot if PUT /v1/schedule lands during execution window  ✅ RESOLVED

**Resolution (2026-04-30):** Moved the `next_run_at` advancement out of `_tick` (which computed against a stale config snapshot taken at tick start) and into `record_run`. `record_run` now takes `advance_now` (an instant) instead of `advance_to` (a precomputed value) and recomputes against the freshly-loaded config row. A PUT that lands during a tick is honored on the way out — no more lost slots, no `is_running` flag needed. See [decisions/011](decisions/011-schedule-mid-tick-put-race.md).

**Files:** `app/schedule/service.py::record_run`, `app/schedule/runner.py::_tick`, plus regression tests in `tests/test_schedule.py`.

---

## DB pruning — eviction for working tables  ⚠️ INTERACTIVE TRIGGER

**Status:** Open (captured 2026-04-30). Not urgent at current scale (~300–400 MB total).

**Why deferred:** Trust-bearing tables (`prediction_accuracy`, `trades`, `drift_alerts`)
deliberately have no TTL — full history is needed for drift detection and per-rule P&L
attribution. Working tables (queue, fetch_misses, ineligible tasks, old 1h OHLCV) grow
forever by accident, but the volume is small enough that pruning is premature.

**⚠️ When the operator triggers this item, the implementer MUST present all four options
below and ask which to implement. Each has different reversibility and behavioral
implications. Do not silently bundle them.**

| # | Target | Policy proposal | Implication |
|---|---|---|---|
| 1 | `submit_queue` | Prune rows where `status IN ('completed','cancelled') AND updated_at < now() - 30d` | Loses queue history (job-id → enqueue-source mapping for audit). Safe — completed work is already mirrored in `analysis_jobs`. |
| 2 | `analysis_tasks` (ineligible-only) | Prune rows where `status='ineligible' AND finished_at < now() - 90d` | Loses ineligibility forensics ("why didn't NEE@1h fire 4 months ago?"). Acceptable if `_process_task` keeps logging the reason on each new attempt. Does NOT touch `done`/`error` tasks. |
| 3 | `ohlcv_fetch_misses` (resolved-only) | One-shot cleanup: delete rows where an `ohlcv_bars` row exists at the same `(ticker, interval, target_ts)` | Forensic-only impact. Keeps the table as "list of bars that genuinely never published". Recommended one-shot, then schedule monthly. |
| 4 | `ohlcv_bars` 1h history beyond 90 days | Prune rows where `interval='1h' AND ts < now() - 90d` | **Highest impact.** Disables 1h-cadence backtests beyond the window. Do NOT pick this if any active hypothesis uses 1h ratios for confirmation. Reversible only by re-fetching from yfinance (which has its own 730d cap). |

**Trigger to revisit:** total DB > 5 GB OR restore-from-dump > 60s OR Railway storage tier
forced upgrade. None currently true.

**Implementation pattern:** for #1–#3, add a lifespan loop similar to `sync_outbox.purge_loop`
with a per-table retention setting in `app/core/config.py`. For #4, a one-shot SQL migration
plus an ongoing rule in `_collect_actuals` that re-anchors the 1h refresh window.

**Files involved:** `app/queue/service.py`, `app/analysis/service.py`,
`app/accuracy/service.py`, `app/market_data/service.py`, `app/core/config.py`.

---

## Move `Base.metadata.create_all` out of lifespan; add boot-time alembic-version warning  ✅ RESOLVED

**What:** Two related cleanups to the schema-bootstrap path:

1. Remove `Base.metadata.create_all` from [`app/main.py`](../app/main.py) lifespan; tests still build their schema from models in `tests/conftest.py`. Production / laptop boots no longer silently auto-create tables.
2. Add a boot-time `WARN` when `alembic_version.version_num` != the latest revision file under `migrations/versions/`. Doesn't mutate, doesn't raise — just surfaces drift.

**Resolution:** Shipped 2026-05-02 (after second occurrence of the boot-vs-alembic race in 24 hours: M-2 on 2026-05-01 + Phase 2 on 2026-05-02). New module [`app/core/schema_check.py`](../app/core/schema_check.py) provides `warn_if_drift(engine)`, called from lifespan in place of the old `create_all` block. Five new tests cover silent / warn-when-missing / warn-on-mismatch / silent-on-match / against-real-repo. Live laptop boot at version `0022` confirmed silent; simulating `version_num='0019'` produced `[schema] DB at revision 0019; latest on disk is 0022. Run alembic upgrade head ...`.

`tests/conftest.py` is now the *only* place `Base.metadata.create_all` is called — annotated as such.

[`.claude/laptop-setup.md`](laptop-setup.md) updated to make the `alembic upgrade head` step explicit-and-mandatory.

**Original decision rationale preserved:** the silent-drift class of bug (column added in migration but `create_all` built the table without it) almost never bites, but when it does it's invisible until prod. Removing the parity-net trades a tiny bit of first-boot DX for a much better drift posture. CI round-trip migrations were considered and rejected as overkill at solo-operator volume.

**Files touched:** `app/main.py`, `app/core/schema_check.py` (new), `tests/test_schema_check.py` (new), `.claude/laptop-setup.md`.

---

## Vision retrieval over original sources (PDF page-image, video frame)

**What:** A new `/v1/research/deep-dive?vault_path=X&page=Y` (or `&timestamp=Y`) endpoint that uses a vision-capable model to read a specific page of the original PDF/EPUB, or a specific timestamp range of the original video, to answer fact-check or chart-extraction questions text-RAG can't (chart values, equation transcription, table fidelity, figure interpretation).

**Status:** Open. Breadcrumb already in place — every PDF/EPUB-ingested note carries `source_path` + `source_sha256` (and `source_pdf_pages_total` for PDFs); videos and newsletters carry `source_url`. The retrieval path is what's deferred.

**Why deferred (2026-05-02 brainstorm):** "If we might want X, we should build X" is the most common reason solo-operator side projects accumulate dead infrastructure. The current stress-test loop reasons over claims that live in prose; charts in books are usually illustrative not load-bearing. Building vision retrieval before the operator hits a real "I needed to see chart X and couldn't" moment risks designing for the wrong query shape.

**Trigger to revisit:** Operator can name **3 concrete instances** within a single 2-week window where they wanted a fact-check or chart value from a source and the existing markdown bundle didn't have it. That's strong-enough signal to design the retrieval shape against real queries instead of imagined ones.

**Order-of-likelihood by source type:**
1. **Videos** — Whisper transcripts lose ~100% of visual content (FRED screenshots, technical chart annotations, holdings tables). The largest gap if this matters at all.
2. **PDFs** — body prose survives, charts/equations/tables don't. Books' charts are usually illustrative; financial reports' charts are sometimes load-bearing.
3. **EPUBs** — mostly text anyway; lowest gap.
4. **Newsletters (web)** — text-heavy; lowest gap.

**Implementation pointers when triggered:**
- Frontmatter breadcrumb already exists (PDF: `source_path` + `source_sha256` + `source_pdf_pages_total`; EPUB: `source_path` + `source_sha256`; video/newsletter: `source_url`). No re-ingest needed.
- For PDFs: `pymupdf` already used for text extraction; same lib renders pages to PNG via `page.get_pixmap()`.
- For videos: yt-dlp can fetch a frame range; `ffmpeg` extracts at-second frames.
- Endpoint: pick the source via `vault_path` lookup → resolve via `source_path` (or re-locate via `source_sha256` if file moved) → render the page/frame → call vision-capable Claude with the rendered image + the operator's question.
- Persistence: same `research_queries` table with a new `kind: deep_dive` discriminator. Same approval flow if any DSL change is proposed.
- Output: same Obsidian markdown answer with the rendered page embedded (Obsidian renders images natively from data URI or `attachments/` path).

**Files involved (when triggered):** `app/research/deep_dive.py` (new), `tools/vault_indexer/ingest/ingest_pdf.py` (re-locator helper if files move), `app/research/routes.py` (new endpoint).

**NOT doing now:** copying PDF/EPUB files into the vault. Vault stays markdown-only; original files stay in operator's library. The breadcrumb is enough.

**Candidate embedder stack (decision deferred to trigger time)** — added 2026-05-02 after the LightRAG/Gemini comparison ([`plans/i-want-to-compare-declarative-kazoo.md`](plans/i-want-to-compare-declarative-kazoo.md)):

| Option | Dim | Cost (~6000 page-images one-time) | Pros | Cons |
|---|---|---|---|---|
| **Gemini `multimodalembedding@001`** (Vertex) | 1408 | ~$1.20 | Broader training corpus (charts, infographics, financial graphics); shared text/image space; managed; current quality leader | Page images leave the laptop on every embed; API dependency; pay-per-call ongoing |
| **Local CLIP / SigLIP** (`transformers`) | 512–1024 | $0 | Fully local — privacy preserved; no API outage risk; no per-call cost | Narrower training distribution; lower quality on financial charts specifically; more setup (model weights + pipeline) |

Pick at trigger time based on which trade-off matters more. If the operator is willing to send page images of their books to Google for the quality gain → Gemini. If privacy is non-negotiable → local CLIP/SigLIP. The retrieval shape is identical either way: render PDF page → embed → store in a *separate* sqlite-vec virtual table (different dim, different model) → query both text and image indexes, merge results.

**Decision NOT to use Gemini for text embeddings:** see [`plans/i-want-to-compare-declarative-kazoo.md`](plans/i-want-to-compare-declarative-kazoo.md). bge-large-en-v1.5 stays for the text path; Gemini multimodal is purely an option for the image-modality path that doesn't yet exist.

---

## Entity-extraction-into-frontmatter (LightRAG-lite)

**What:** A cheap structural steal from LightRAG without buying the full graph machinery. At ingest time (alongside the existing `auto_tag.py` Claude Haiku call), extract a short list of named entities per note (`entities: [Lyn Alden, BTC-USD, MSTR, debasement]`) and store them in frontmatter. At retrieval time, use the entity list as a **filter** alongside the cosine KNN: "given query mentions BTC-USD, prefer chunks whose parent note has BTC-USD in `entities`."

This adds entity-aware retrieval without:
- Building / maintaining a knowledge graph
- LLM-in-the-retrieval-path latency (extraction is at ingest, not query)
- Schema migrations beyond a frontmatter field
- The dual-retrieval ranking-merge complexity LightRAG carries

Quality trade-off vs full LightRAG: weaker — no entity-relation graph, no multi-hop traversal. But meaningfully better than today on entity-boundary cases the current pure-vector retriever fumbles ("everything Lyn says about Bitcoin specifically, not crypto broadly").

**Status:** Open. Deferred 2026-05-02 after the LightRAG / Gemini comparison (see [`plans/i-want-to-compare-declarative-kazoo.md`](plans/i-want-to-compare-declarative-kazoo.md)).

**Why deferred:** No active failure. The Phase 3 stress-test loop is single-thesis-shaped and the current vector retrieval handles single-source queries well. Building entity-aware filtering before the operator sees a query that would benefit from it is anticipatory infrastructure — same trap as full LightRAG, smaller blast radius.

**Trigger to revisit:** First time the operator writes a query and `/research/ask` returns evidence that's topically adjacent but entity-wrong (e.g. asking about MSTR-mNAV gets generic crypto chunks instead of MSTR-specific ones). One concrete failure → re-open.

**Cost estimate when triggered:**
- ~50 lines of new code in `tools/vault_indexer/entity_extract.py` mirroring `auto_tag.py`'s structure
- ~$1/yr in Haiku calls at expected ingest volume (one call per ingest, 1-5 entities returned)
- One additional frontmatter field (`entities`); one additional query-side filter pass in `search.py`
- ~2 hrs total

**Why NOT just go straight to full LightRAG:** see the comparison plan for the full reasoning. Short version: the graph machinery's wedge is multi-hop / cross-source queries we don't yet have. The entity-list-as-filter captures ~70% of the entity-aware win at ~5% of the cost and complexity.

**Files involved when triggered:** new `tools/vault_indexer/entity_extract.py`, edits to `tools/vault_indexer/indexer.py` (call extract during ingest), `tools/vault_indexer/search.py` (entity-filter at retrieval), `tools/vault_indexer/auto_tag.py` (might share the LLM call to avoid double-calling).

---

## How to add an entry

Use the same structure: **What** / **Status** / **Why deferred** (or **Open**) / **Trigger to revisit** / **Implementation pointers**. Include the key files involved so future-you doesn't have to re-derive context.
