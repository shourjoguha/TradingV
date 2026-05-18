# How to use this platform

End-to-end walkthrough — first-run setup, the daily loop, and the diagnostic flowchart when something looks off. Read the **Metrics & Definitions** tab if you hit a term you don't recognise.

---

## What this platform is (60 seconds)

A trading-decision-support system. One operator (you). Two halves:

1. **Forecast pipeline** — daily Kronos predictions on a watchlist, scored against actuals, distilled into BUY/SELL signals. The numbers half.
2. **Context layer** — what you're paying attention to. TV Context inputs (notes / ideas / screenshots / events), hypotheses you're tracking, smart-money snapshots, macro regime panels, vault-grounded research. The narrative half.

The two halves meet at the **rx finance** tab (Decide → Motion → Recs): one ranked recommendation a day, sourced from both halves, with an attention badge showing which of your manual inputs drove it.

The platform does NOT execute trades. You log them manually so it can attribute realised P&L back to the rules that suggested the signal.

![Three-layer architecture — input sources feed three parallel process lanes (forecast / knowledge / context) which converge at the rx finance decision surface](/docs-visuals/architecture.svg)

---

## First-run setup

### 1. Pick a watchlist (Decide → Watchlist)

Start with 5–15 tickers. The daily scheduler iterates this list, so every name here pays a cost in compute + API quota. Avoid the "100-ticker FOMO list" — pick names you'll actually trade.

Optional: organise thematic baskets as **Boards** ("AI infra", "rate-sensitive", "earnings this week"). One ticker can sit on the roster + N boards independently. Boards drive the **operator universe** used by ticker auto-extraction and rx attention scoring.

### 2. Enable the schedule (Admin → Schedule)

Set `run_at_local` to a time after market close in your timezone. Default `23:30 UTC`. Toggle `skip_weekends` on (weekend predictions for stocks are wasted compute).

Wait one full day. The pipeline needs at least one settled bar before the Accuracy heatmap shows anything meaningful.

### 3. Wire your `.env.laptop` (one-time)

The platform runs locally with a Tailscale replica on Railway. Required env vars:

| Var | What | Notes |
|---|---|---|
| `DATABASE_URL` | Postgres connection | Use docker-compose Postgres on `:5439` for laptop |
| `API_KEY` | Frontend ↔ backend auth | Any random string |
| `ANTHROPIC_API_KEY` | Research + TV-context vision | Optional but unlocks Research tab |
| `RX_INGEST_TOKEN` | `/rx-finance` slash command → TradingV | Separate from API_KEY so it can be rotated independently |
| `INSTANCE_NAME=laptop` | Required for lifespan loops to fire | Railway sets `INSTANCE_NAME=railway` |
| `VAULT_PATH` | Path to your knowledge-vault Obsidian root | Defaults to `~/Documents/knowledge-vault` |

Optional video-vision deps: `brew install tesseract` for OCR (see Vault section in **Metrics & Definitions**).

### 4. Start the stack

```bash
./run-dev.sh
```

Wait for `✓ stack up`. Logs at `.dev-logs/{backend,frontend,indexer}.log`. Stop with `./run-dev.sh stop`.

---

## The daily loop

A morning ritual that should take 10–20 minutes once the platform has a week of data.

### Step 1 — Open **Today** (`/`)

Single-screen catch-up. Skim top to bottom:

1. **Drift banner** — any `(ticker, horizon, model)` pair whose recent MAPE blew up? Acknowledge or click through to Accuracy heatmap for context.
2. **Pending research approvals** — Claude has stress-tested a hypothesis. Read the verdict, approve or dismiss.
3. **Fresh signals strip** — new entries on the Motion → Signals list since you last visited.
4. **TV Context strip** — recent notes/ideas/screenshots/events for tickers you care about.
5. **rx strip** — top 3 open recs ranked `forced > aging > drift_score desc`. Click any to disposition.
6. **Ticker review queue** — unknown tickers extracted from video transcripts or TV-context that haven't been added to roster yet.
7. **Inbox aggregate** — counts of what's awaiting your attention across all the above.

Each strip hides itself when empty. If Today looks sparse, you're caught up.

### Step 2 — Disposition open recs (Motion → Recs)

Each rec has:
- A **drift score** (0–1) — generator's risk read.
- A **confidence** (0–100).
- A **tldr** + **body_md** narrative.
- An **operator-attention badge** if your recent TV-context items mention any ticker in the rec — closes the feedback loop on your screenshot effort.
- Cross-references — linked hypotheses + recent trades on mentioned tickers.

Click in. Read. Then:

- **Act** — pick `acted_as_prescribed` / `acted_modified` / `skipped`. The first two require a `subjective_fit_1_5` rating (your gut-check). Optional outcome note.
- **Snooze** — punt 1–7 days. After 2 snoozes the rec is flagged "forced decision" — you must disposition next time, no more snoozing.
- **Dismiss** — operator chose not to act.

If you acted, click **"Log trade from this rec"** — the trade form prefills with the rec's ticker + a `related_rec_id` link. One save closes the loop for per-rule P&L attribution.

### Step 3 — Drop context (TV Context)

Anything you noticed today that the price feed wouldn't catch:

- **Note** — text. "Watching for a wedge break on NVDA 4H."
- **Idea** — paste a TradingView idea URL. Optional summary.
- **Screenshot** — paste / drag a chart image. Optional caption. Optional Claude vision summary (~$0.005/img).
- **Event** — dated catalyst. "FOMC Wed. Watch JPM."

When you flag a screenshot or note against a specific hypothesis, pick a **stance**: `supports` / `challenges` / `context`. Stance-flagged screenshots feed the hypothesis invalidator DSL — 2+ "challenges" screenshots in 14 days can auto-invalidate a thesis (configurable per hypothesis).

If you typed a ticker outside your operator universe (roster ∪ boards ∪ The Street tier-1/2), the ticker auto-lands on the **review queue** for next-day promotion.

### Step 4 — Check the regime (Decide → Macro)

Six panels: Inflation / Growth / Liquidity / Stress / Inflation regime / Yield curve. Click any row to expand a 5-year chart. Hover the `(i)` for operator-tuned thresholds (e.g. "30Y >5% sustained = fear-of-unknown").

Use this when you're deciding whether to trust today's signals. Macro regime sets the prior for everything downstream.

### Step 5 — End of day — log trades you made elsewhere

If you traded through a broker without using the "Log trade from this rec" flow, hit **Decide → Motion → Trades** and add the entry manually. Mark closes when you exit. Realised P&L flows automatically through to per-rule attribution.

---

## When you have time — deeper workflows

### Investigating a prediction (Predictions → By Horizon)

You want to know if NVDA's `+5d` prediction is trustworthy:

1. Open `/predictions/horizon` → search NVDA, pick the made-on date.
2. Look at the Δ% color — was the model conservative, aggressive, or on the money historically?
3. Switch to **Accuracy** tab — what's the hit rate + MAPE for `(NVDA, 5d, kronos, 1d)` over the last 30 evaluations?
4. If yellow or red, don't act on the signal. If green, cross-check the **Drift** banner — was this pair recently flagged?

### Stress-testing a thesis (Think → Research)

You want to challenge a hypothesis before committing capital:

1. Open `/research` → pick the skill (default `research-stress-test`).
2. Type the question. Optionally select a hypothesis to link.
3. Submit. Claude bundles evidence from your vault + macro + The Street snapshots and returns a verdict with a `proposed_action` (e.g. "patch invalidator: 30Y > 5.5% for 14d").
4. Approve → action applies. Dismiss → logged + the system learns from the rejection.

If the query depends on operator context and your TV Context for the linked tickers is empty, the pipeline short-circuits with status `needs_context` instead of inventing a verdict. Drop a screenshot or note first.

### Reading The Street (Think → The Street)

Three modes:

- **Latest tier list** — what's smart money buying this week? Tier 1 = high-conviction multi-channel buys.
- **Per-ticker timeline** — has insider buying picked up on a name you're watching?
- **Snapshot browser** — click any dated snapshot to read the full `_index.md`.

Tier 1 / Tier 2 names auto-merge into your operator universe — they don't pollute your roster, but the ticker auto-extractor knows them.

### Vault search (Think → Research → search bar)

Type a free-text query. Hybrid retrieval:
- Vector KNN over BGE-large embeddings on every markdown chunk.
- FTS5 lexical BM25.
- Query parser extracts hard anchors (tickers, kinds, time phrases) and narrows the candidate pool.
- Two ranked lists merged via RRF.

Click any hit to read the source chunk + jump to the canonical file in Obsidian.

---

## When something looks wrong — diagnostic flowchart

### Drift banner won't go away
**Symptom:** an alert keeps re-firing on the same pair.
**Cause:** acknowledging an alert doesn't fix the underlying drift; it just dismisses the surface. The pair is still degrading.
**Action:** open the Accuracy heatmap for that pair → drill into recent predictions → look for a regime change in the made-on dates. If you can pinpoint the start, consider whether the model needs retraining or whether the regime is temporary.

### Today strip says "no fresh signals" but you expected some
**Symptom:** Motion → Signals list is shorter than yesterday.
**Cause:** either no predictions met the rule thresholds (`+2% over 5d, HR ≥ 60%` etc.) OR the daily run was deferred (queue full).
**Action:** check **Admin → Processes → schedule** — was the last tick successful? If `pending_run` is set, the runner is retrying. If status is red, click into the error.

### rx rec has `attention_score = 0` but you screenshotted that ticker
**Symptom:** rec on NVDA has no attention badge even though you dropped 2 screenshots last week.
**Cause:** attention is stamped at rec **creation time**. If the rec landed BEFORE your screenshots, it didn't see them.
**Action:** generate a new rec via `/rx-finance` on the laptop. The next rec mentioning NVDA will pick up the attention.

### Vault search returns nothing
**Symptom:** Research tab → search → empty results.
**Cause:** vault indexer probably isn't running on port 8001, OR the cache hasn't been rebuilt since you added new content.
**Action:** check the indexer log (`.dev-logs/indexer.log`). If it's down, restart via `./run-dev.sh`. If it's up but stale, `curl http://localhost:8001/reload`.

### Claude API returns 503
**Symptom:** Research or vision call fails with 503.
**Cause:** either the global Anthropic kill-switch tripped (Admin → Costs hit monthly cap) OR you haven't set `ANTHROPIC_API_KEY`.
**Action:** check Admin → Costs. If progress bar is at 100%, either raise the cap or wait for next month. If under cap, verify env var.

### Trade form's "Related rec" dropdown is empty
**Symptom:** trying to link a trade to a rec but no recs show.
**Cause:** dropdown filters to **finance recs from the last 30 days only**.
**Action:** older recs need to be linked via the URL deep-link from rec detail ("Log trade from this rec").

### Ticker review queue keeps re-suggesting the same dismissed ticker
**Symptom:** you dismissed `BABA` last month but it's back.
**Cause:** dismissed entries can re-surface IFF re-encountered AND 90 days have passed.
**Action:** dismiss again, OR if the re-mention is meaningful (new context), add to roster / a board.

### Backend won't start: `alembic upgrade head` fails
**Symptom:** uvicorn crashes on startup with a missing-revision error.
**Cause:** local migration chain out of sync with code. Usually a stale checkout missing a new migration file.
**Action:** `git pull && ./venv/bin/alembic upgrade head`. If still broken, `./venv/bin/alembic history` shows the chain — check for a gap.

### Frontend builds locally but TypeScript errors fly on a fresh clone
**Symptom:** `npx tsc --noEmit` clean on your laptop, errors on CI / fresh clone.
**Cause:** an untracked file is satisfying an import on your laptop. Common after stashed-and-restored sessions.
**Action:** `git status` → look for untracked `.tsx` files. If they're referenced by tracked code, commit them (or remove the import).

---

## Cost mindfulness

The platform consumes Claude API for two paths:

- **Research stress-tests** — Claude Sonnet, ~$0.05–0.50 per query depending on bundle size.
- **TV-context vision** — Claude Sonnet vision, ~$0.005 per screenshot at 1024px.

**Default monthly cap: $5.** Auto-flips both kill-switches at 100%. Adjust via Admin → Costs.

Things that DON'T cost money:
- Predictions (Kronos runs locally).
- Vault search (BGE embeddings local; FTS5 + vector index local).
- Macro / The Street / opportunities / accuracy — all local compute.
- yfinance / FRED / EDGAR / NASDAQ — free public APIs.

If your monthly bill creeps up, the Costs tab shows per-class breakdown. Vision tends to be the bigger line when screenshot ingestion is heavy.

---

## Where things live

| You want to... | Go to |
|---|---|
| See today's catch-up | `/` (Today) |
| Disposition a rec | Decide → Motion → Recs |
| Log a trade | Decide → Motion → Trades |
| Check model accuracy | Decide → Predictions → Accuracy |
| Read the regime | Decide → Macro |
| Drop a chart / note | Think → TV Context |
| Track a thesis | Think → Theses |
| Stress-test an idea | Think → Research |
| See smart-money flow | Think → The Street |
| Tune cadences / costs | Admin → Cadences / Costs |
| Learn what a term means | Docs → Metrics & Definitions |

---

## What's NOT in scope (yet)

- **Live order execution** — out of scope forever. You decide; you execute on your broker.
- **Multi-user** — single-operator system.
- **Streaming intraday data** — daily-close cadence only.
- **Mobile apps** — desktop web only.

If you want a feature, log it as a hypothesis (`Think → Theses`) or a note (`Think → TV Context`) so it doesn't get forgotten.
