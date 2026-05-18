# Metrics & Definitions

Plain-language reference for every term, ratio, color, and concept across the platform. Bookmark this page; click any heading in **On this page** to jump.

![Two halves of the platform — forecast pipeline and context layer — converging at rx finance](/docs-visuals/hero-stack.svg)

This doc is grouped by **what part of the platform you're looking at**, not alphabetically. Skip to **Glossary** at the bottom for an A–Z index.

---

## Predictions

### Prediction
A model's forecast for a single ticker, single bar interval, single future timestamp. Each prediction carries an OHLCV tuple (`open`, `high`, `low`, `close`, `volume`) — the model's best guess for that bar's actual values.

### Horizon (`T-N`, `+Nd`, `+Nh`)
How many bars into the future the prediction is for, counted from the day it was made. `T-1` means "the next bar", `T-5` means "five bars ahead". Longer horizons are harder; we track each separately.

### Made-on date
The day the prediction was generated. A prediction made on Monday for `T-1` targets Tuesday's bar.

### Target date
The day the prediction is for. Used to pair the prediction against the eventually-published actual bar.

### Forecast (vs. settled)
- **Forecast cell** — the target date hasn't passed yet; only the prediction exists. By Horizon shows the predicted close in italics with a dashed border and a `→` arrow.
- **Settled cell** — the target has passed and the actual bar is in the cache. Shown with the Δ% color (see below).

### Δ% (Delta percent) — the By Horizon cell value
How far the prediction was from the actual, as a percentage of the actual close.

```
Δ% = (predicted_close − actual_close) / actual_close × 100
```

Reading the sign:
- `+1.5%` → prediction was **above** the actual (overshoot).
- `−1.5%` → prediction was **below** the actual (undershoot).

Color thresholds:
- 🟢 Green — undershoot (`Δ < −1%`). Model was conservative.
- 🔴 Red — overshoot (`Δ > +1%`). Model was bullish-er than reality.
- ⚪ Grey — within `±1%`. Effectively on the money.

---

## Accuracy

The Accuracy page summarises model performance per `(ticker, horizon, model, interval)` over a rolling window. Two numbers per cell, plus a sample count.

### Hit rate (directional accuracy)
The fraction of predictions whose **direction** matched reality, ignoring magnitude.

```
hit_rate = directionally_correct_predictions / total_predictions
```

A prediction is "directionally correct" when it agreed with the actual move from the baseline (close on the made-on day):

```
predicted_dir  = sign(predicted_close − baseline_close)
actual_dir     = sign(actual_close    − baseline_close)
direction_correct = (predicted_dir == actual_dir)
```

### MAPE — Mean Absolute Percentage Error
The average size of the prediction miss, regardless of direction.

```
MAPE = mean( |actual_close − predicted_close| / actual_close )
```

Lower is better. `2%` MAPE means the average prediction is off by 2% of the actual close.

### Why both? — and the "lucky-but-wrong" trap
A model that always says "up" can score `100%` hit rate on a steadily rising stock while still being economically useless because every individual call is far from the actual close. Pairing **hit rate** with **MAPE** stops the operator from being tricked by directionally-lucky-but-magnitude-wrong models.

That's why each Accuracy cell shows `<hit%> / <MAPE%>` and uses a composite color:

- 🟢 Green — `hit ≥ 60%` **AND** `MAPE ≤ 2%`. Reliable.
- 🟡 Yellow — neither rock-solid nor broken. Watch.
- 🔴 Red — `hit < 50%` **OR** `MAPE > 4%`. Don't trust it yet.
- ⚪ Grey — `n < 4`. Insufficient sample size.

### RMSE — Root Mean Squared Error
The dollar-magnitude version of MAPE: how far off in price units.

```
RMSE = sqrt( mean( (actual_close − predicted_close)^2 ) )
```

Computed but not shown on the heatmap (visible in the per-cell hover tooltip). RMSE penalises big misses more harshly than small ones.

### `n` — sample count
How many evaluated predictions are in this cell. Small `n` makes the rate noisy: with `n=4`, the only possible hit rates are `0%, 25%, 50%, 75%, 100%`. Cells with `n < 4` are greyed-out to avoid misleading you.

### Window
The rolling window selector (`last 10 / 30 / 100 / 500`) limits how many of the most-recent evaluations contribute. Smaller windows track recent behavior; larger windows smooth out noise.

### Interval
`1d`, `1h`, etc. The bar cadence of the prediction. The toggle on the Accuracy page splits cadences so a 1h-cadence model isn't averaged with a 1d-cadence one.

---

## Drift

A change in a model's recent error pattern that suggests something has shifted (regime change, data quality issue, model staleness).

### Recent vs. all-time MAPE
The drift detector compares **recent MAPE** (last 30 days) against **all-time MAPE** for the same `(ticker, horizon, model)`. If recent is meaningfully worse, the pair is flagged.

### Drift ratio
```
ratio = recent_mape / all_time_mape
```

### Threshold
A pair is flagged when:

```
ratio ≥ 1.5  AND  recent_n ≥ 10  AND  all_time_n ≥ 30
```

The two `n` floors protect against statistical fluke flags.

### Acknowledge
Open drift alerts surface as a banner on the Accuracy page. **Ack** dismisses the current alert and unblocks future re-flags for the same pair.

---

## Signals (Motion → Signals)

Daily list of predictions that survived a battery of rules and look actionable. Lives under **Motion → Signals** (operator-facing name for what the backend calls "opportunities").

### Rule
A boolean check on a prediction. Today's three production rules:

- **BUY ≥ +2% over 5d, HR ≥ 60%** — predicted move at least +2% on the 5-day horizon, plus historical hit-rate on that pair already ≥ 60%.
- **SELL ≤ −2% over 5d, HR ≥ 60%** — same shape, bearish.
- **BUY ≥ +5% over 10d, HR ≥ 55%** — longer horizon, more permissive HR floor.

Each fired rule carries its own historical hit rate. Composite score = sum of fired rules' hit rates.

### Baseline close
The close on the made-on day. Anchors "did the prediction expect movement?" — without a baseline we can't tell direction.

### Predicted move %
```
predicted_move_pct = (predicted_close − baseline_close) / baseline_close × 100
```
Positive = bullish call. Negative = bearish.

### Weighted score
```
score = sum( hit_rate_of_each_passing_rule )
```

### Generation
Daily after end-of-day OHLCV ingest (cadence reduced from hourly 2026-05-16 per cost audit). Manual fire via the Admin → Processes tab.

---

## Trades

Manually logged buy/sell entries. The platform doesn't execute trades — you do — but logging closes the loop so the platform can attribute realised P&L back to the rules that suggested the signal.

### Open vs. closed
- **Open** — entry recorded, no exit yet. Shows unrealised P&L (if a recent OHLCV close is cached for the ticker).
- **Closed** — exit recorded. Realised P&L is final.

### Realised P&L
```
realised = (exit_price − entry_price) × size × side_sign
```
where `side_sign = +1` for long, `−1` for short.

### Unrealised P&L (open positions)
```
unrealised = (latest_ohlcv_close − entry_price) × size × side_sign
unrealised_pct = unrealised / (entry_price × size)
```
Falls back to entry-price (zero P&L) when no quote is cached for the ticker yet.

### Per-rule attribution
Each closed trade attributes back to the rules that fired on the signal that triggered it. Per-rule P&L tells you which rules actually made money — not just which had high hit rates.

### `related_rec_id` (rx finance linkage)
Optional FK from a trade to a finance recommendation (see **rx finance** below). Populated by the "Log trade from this rec" CTA on rec detail. Surfaces as a clickable short_id badge on the Trades table.

### Positions (`/motion/positions`)
Per-ticker aggregation of open trades: qty, avg entry price, current value, percent of portfolio. `current_price` falls back to entry-price when no daily OHLCV is cached. Per-ticker `unrealized_pnl` + portfolio-level aggregate displayed as 3-card header.

### Risk flags
- **`risk_flag_single`** — single position > 5% of portfolio. Suppressed when `portfolio_value < $5,000` OR `open_positions < 4` (no cry-wolf on a sparse book).
- **`risk_flag_sector`** — stub; sector lookup table not yet built. Always False today.

---

## TV Context

The operator's manual context layer — what they're paying attention to that doesn't show up in price action. Five input kinds, all polymorphic rows on `tv_context_items` with per-kind retention:

| Kind | What | Retention |
|---|---|---|
| **note** | Free-form text about a ticker | 180d |
| **idea** | Saved TradingView idea URL + optional summary | 180d |
| **screenshot** | Chart image + operator caption (+ optional Claude vision summary) | 30d |
| **event** | A dated catalyst (earnings, FOMC, etc.) | event_date + 30d |
| **webhook** | TradingView Pine alert payload | 7d (with rolling-window dedupe) |

### Stance (on hypothesis links)
Operator can flag a TV-context item against a specific hypothesis. Three stances:

- **`supports`** — evidence FOR the hypothesis.
- **`challenges`** — evidence AGAINST. Operator-facing equivalent of "evidence against".
- **`context`** — relevant but not directional.

Used by the hypothesis invalidator DSL (see below).

### Vision summary (screenshots only)
On screenshot upload, an optional Claude Sonnet vision call summarises the chart in markdown. Per-call cost ~$0.005 at 1024px wide. Toggle per-upload + global monthly cap via Admin → Costs.

### Ticker review queue (parity)
When you submit a note/idea/screenshot/event with a ticker NOT in your universe (`roster ∪ boards ∪ The Street tier-1/2`), the unknown ticker is enqueued to the ticker review queue. Webhooks are skipped (alert rule already pre-filtered).

---

## Hypotheses (Theses)

A trackable claim about a regime, breakout, tactical setup, or single name. Lives under **Think → Theses**. Each hypothesis has:

- **`slug` / `title` / `body_md`** — narrative content (markdown).
- **`claim_type`** — `regime` (30mo TTL) / `breakout` (30mo) / `tactical` (6mo) / `single_name` (18mo).
- **`axis`** — free-form bucket label (e.g. `liquidity`, `inflation`, `equity:AAPL`).
- **`primary_metric` / `tracking_signal`** — what to watch.
- **`invalidator`** — DSL spec that auto-flips status when triggered.
- **`expires_at`** — TTL from `claim_type`.

### Status lifecycle
- **`active`** — under evaluation.
- **`invalidated`** — invalidator fired.
- **`expired`** — TTL passed without invalidation or manual close.
- **`cancelled`** — operator manually cancelled (e.g. preconditions broken).
- **`manual_closed`** — operator dismissed via `/cancel`.

### Invalidator DSL
Single shape: `{op, args}`. Daily `_hyp_tick` loop evaluates every active row. Seven ops:

| Op | Args | Fires when |
|---|---|---|
| `ratio_below_sma` | `numerator, denominator, sma_days, days_below` | Ratio (a/b) below its N-day SMA for K consecutive days |
| `series_above_threshold` | `symbol, threshold, days_above` | Macro series > threshold for N consecutive days |
| `series_below_threshold` | `symbol, threshold, days_below` | Mirror, strict `<` |
| `series_change_pct` | `symbol, window_months, threshold_pct, direction` | % change over window exceeds threshold in direction |
| `manual` | `{}` | Never auto-fires. Operator dismisses via `/cancel` |
| `tv_context_count_since` | `days, min_count` | ≥ min_count `HypothesisTVContextLink` rows in trailing window |
| `tv_context_stance_count_since` | `days, stance, min_count` | Same, filtered to a specific stance |

When an invalidator fires, status flips to `invalidated` and a `HypothesisEvaluation` row records the reason.

### Cascade
Hypotheses can declare a `precondition_id` pointing at another hypothesis. When the parent becomes non-active, dependents flip to `cancelled` (recursive, bounded at 10 iterations to break cycles).

### Health view (`/theses/health`)
Per-hypothesis age, days-to-expiry, count of recent (last 30d) finance recs whose `tldr|body_md` mentions the hypothesis title (substring match, min length 3). Substring-based — false-positive prone but cheap.

---

## Macro Workbench

Daily-close macro series (yfinance + FRED) with regime panels for at-a-glance read. Lives under **Decide → Macro**. Six panels:

1. **Inflation** — CPI, PPI, mortgage spread, gold/silver ratio.
2. **Growth** — yield-curve proxies, copper/gold ratio.
3. **Liquidity** — WALCL, M2, reverse-repo levels.
4. **Stress** — VIX (equity vol), **MOVE** (bond vol), credit spreads.
5. **Inflation regime** — gold vs. real-rates composite.
6. **Yield curve** — 2Y / 10Y / 30Y treasury + 2s10s spread + 10y-3m spread (NY Fed recession-probability model input).

### Series shapes
- **Raw series** — one symbol, sparkline of latest values.
- **Ratio** — `a / b`, weekday-aligned (avoids stale-Friday bias).
- **Spread** — `a − b`, weekday-aligned (used for yield-curve panel).

Click any row to inline-expand a focused 5-year line chart. Hover the `(i)` icon for the operator-tuned directional guidance (e.g. "30Y >5% sustained = fear-of-unknown").

### Regime
A multi-month / multi-quarter market state that biases ratios and asset returns systematically (e.g. risk-on, debasement, recession). The workbench's job is to surface which regime the data is currently in. Not a single number — read across panels.

---

## The Street (smart-money snapshots)

Read-only view of weekly smart-money snapshots aggregated from politician filings, insider trades, hedge-fund 13Fs, and options-flow trackers. Lives under **Think → The Street**. Three browse modes:

- **Latest snapshot tier list** — Tier 1 (high-conviction multi-channel buys), Tier 2 (moderate-conviction), Tier 3 (cluster mentions).
- **Per-ticker timeline** — every Street snapshot row for a given symbol.
- **Snapshot browser** — dated snapshots; each renders its `_index.md` via the vault indexer.

### Tier 1 / Tier 2 universe
Used by the ticker review queue whitelist + rx-finance attention computation.

---

## rx finance (recommendations)

Operator-facing "what should I do next" surface for finance. Lives under **Decide → Motion → Recs**. TradingV is the **exclusive surface for finance recommendations** (fitness + nutrition recs live in a separate Lovable/Supabase app per D-045).

### Lifecycle
Generated on the laptop by the `/rx-finance` slash command (reads live DB: hypotheses + signals + drift alerts + watchlist + vault). Ingested via `POST /v1/rx/recs` with the `X-RX-Ingest-Token` shared secret. Operator dispositions via the UI:

- **`open`** — awaiting decision.
- **`snoozed`** — punted N days (1–7). Snooze count tracked.
- **`acted`** — disposition: `acted_as_prescribed` / `acted_modified` / `skipped`. `acted_*` requires `subjective_fit_1_5` (1–5).
- **`dismissed`** — operator chose not to act.

### Drift score (`drift_score`, 0–1)
Generator-computed risk score for the rec. Higher = more divergence from operator's existing stance. Sort key on the list view.

### Confidence (`confidence`, 0–100)
Generator's self-rated confidence. Surfaced alongside drift.

### Forced decision
A rec snoozed ≥ 2 times. Forces the operator to disposition rather than snooze again — past its useful window.

### Auto-revived
A snoozed rec whose `snoozed_until` has passed. Bubbles back into the open queue automatically.

### Operator-attention axis (`attention_score`, `attention_breakdown`)
Closes the feedback loop: when you screenshotted NVDA last week, the next NVDA-mentioning rec shows a visible 👁️ badge.

![Five decay curves — screenshot/note/idea/event/webhook — each starting at its native kind weight and halving every 7 days](/docs-visuals/attention-decay.svg)

```
score = Σ (kind_weight × exp(-ln2 × age_days / half_life))
      for each TV-context item mentioning any ticker in the rec
```

**Kind weights:**
- `screenshot: 1.0` — highest operator-intent signal
- `note: 0.7`
- `idea: 0.5`
- `event: 0.4`
- `webhook: 0.2` — auto-fired, low intent

**Half-life:** 7 days. Top-level score = MAX across tickers (NOT sum — a rec mentioning 2 tickers shouldn't dilute the heavily-discussed one).

Stamped at rec creation; null on legacy rows.

### Subjective fit (1–5)
Operator's gut-check rating when dispositioning an `acted_*`. Feeds the `/rx-analyze` skill that proposes weight adjustments over time.

### Cross-references
- **Hypotheses** — substring match of hypothesis title in rec `tldr|body_md` (min length 3).
- **Trades** — explicit FK (`trades.related_rec_id`) OR ticker-substring match bounded to open positions OR closed within 90d.

---

## Ticker review queue

Surface for tickers seen outside the operator's universe. Lives on the Today strip + `<vault>/Topics/_ticker-review-queue.md` digest.

Fed by two sources:

1. **Video vision (Stage 1)** — Qwen2-VL emits tickers from chart screenshots in video frames. Anything NOT in roster ∪ boards ∪ The Street tier-1/2 enqueues.
2. **TV Context ingest** — when you submit a note/idea/screenshot/event with a ticker outside that same universe (parity shipped 2026-05-17).

### Surfacing rule
- `times_seen >= 2` distinct sources → surfaces on Today strip.
- Single mention stays in the queue but doesn't pop the strip.

### Resolution
Three atomic actions:
- **Add to roster** — `POST /v1/watchlist`, queue row → `added_to_roster`.
- **Add to board** — dropdown of operator's boards; `POST /v1/boards/<id>/items`, queue row → `added_to_board`.
- **Dismiss** — queue row → `dismissed`.

### Re-eligibility
Dismissed rows can re-surface IFF re-encountered AND `now − resolved_at > 90 days`. UI shows a "previously dismissed YYYY-MM-DD" chip on the re-surfaced row.

---

## Vault (knowledge layer)

Operator-curated markdown corpus under `~/Documents/knowledge-vault/`. Three indexer instances (finance :8001, fitness :8002, nutrition :8003) each maintaining its own SQLite cache. TradingV reads finance only.

### Surfaces consumed
- **`/v1/vault/search`** — hybrid retrieval. Vector KNN (BGE-large embeddings) + FTS5 lexical BM25, RRF-merged. Query parser extracts hard anchors (tickers, kinds, time phrases) and narrows candidate pool before scoring.
- **`/v1/vault/folder-context`** — `_index.md` vignettes along the ancestor chain. Used by research stress-test bundles + Ticker Hub.
- **`/v1/vault/node/{path}`** — read raw markdown for a known path.

### Indexed kinds
`book_chapter` / `video` / `newsletter` / `filing` / `tv_context_*` / `the_street_snapshot` / `folder_context` (`_index.md`) / `research` / `hypothesis`. Each has its own ingest path under `tools/vault_indexer/ingest/`.

### Decay weighting
Vector results are reranked by:
- **Evergreen flag** (operator-set or path-glob default) — bypasses decay, always weight 1.0.
- **Non-evergreen** — per-author rank within `(author, kind)` group; exponential decay across rank 1–N so the fresh newsletter doesn't bury the key Graham chapter.

### Visual notes (video-vision)
Two-channel structured chart extraction on opted-in channels (fx-evolution-daily, click-capital). Scene-detect frames → Tesseract OCR → Qwen2-VL semantic caption. Output: structured chart references (chart_type, timeframe, tickers) auto-enriching the channel's `_index.md` for research bundles.

---

## Research (stress-tests)

Skill-driven query pipeline. Operator asks a question via **Think → Research** or `/v1/research/ask`. Claude Sonnet answers with vault-grounded evidence + a verdict + an optional `proposed_action` (e.g. patch a hypothesis invalidator).

### Skills
Operator-editable markdown files under `skills/research/`:

- **`research-stress-test`** — default. Take a hypothesis, find evidence for + against, propose action.
- **`research-comp-scan`** — peer-rank a ticker against named comparables.
- **`research-earnings-followup`** — post-earnings analysis.

### `requires_tv_context` gate
When a hypothesis or query depends on operator context, set `requires_tv_context=true`. The pipeline short-circuits with status `needs_context` if no recent TV-context items exist for the specified tickers — instead of inventing a verdict with no grounding.

### Approval flow
Queries land in `research_queries` table with status `pending`. Approving the rec via the Today strip applies the `proposed_action` (e.g. patches the hypothesis); dismissing logs the rejection.

---

## Earnings calendar

Rolling per-ticker earnings dates for the operator's universe (`roster ∪ Street tier-1/2`, capped at 150 tickers, 90d TTL). yfinance primary + NASDAQ fallback. EDGAR 8-K Item 2.02 used for `confirmed_at` (US tickers).

Used by:
- **Today panel** — upcoming earnings in next 30 days.
- **IR YouTube channel poller** — only fetches transcripts on T to T+3 of an expected earnings date (cost optimisation).

---

## Schedule

The daily forecast runner.

### `run_at_local`
Wall-clock time (in your `tz_name`) when the runner fires. Default `23:30` UTC.

### `next_run_at`
The next scheduled UTC instant. Recomputed on each PUT and at the end of every tick (always against the freshest config).

### `pending_run`
Set when a run is deferred — most commonly because the analysis queue was full (`AtCapacityError`). The runner retries every `retry_minutes` until `pending_run` clears.

### `retry_minutes`
How often to retry a deferred run. Default `5`.

### `skip_weekends`
When true, the runner skips weekends per ticker asset class. Stocks/ETFs/forex/futures rest; crypto runs every day; unknown asset class is permissive.

### Catch-up
If `next_run_at` is in the past at startup (laptop was off through it), the runner fires once on boot to catch up.

### Fallback (Railway)
Opt-in via `RAILWAY_FALLBACK_ENABLED=true`. If no peer-pushed predictions arrive within `fallback_offset_hours` of the local run-at, Railway runs its own copy.

---

## Admin (loops + costs + retention)

Tabbed shell under **Admin** in the sidebar. Six tabs:

- **Processes** — every background loop with status (last tick, last error, duration), enable toggle, manual fire + abort, confirm-modal for irreversible ops.
- **Cadences** — edit each loop's run-interval. Backed by `app_settings` table; DB wins over env-var defaults.
- **Costs** — monthly Anthropic spend breakdown (research vs. vision), MTD vs. last-month delta, progress against `anthropic.monthly_cap_usd`. Auto-flips kill-switch at 100% cap.
- **Retention** — per data-class TTL + manual purge (capped 5,000 rows per click). Sequenced sweeps: DB first, then vault files, then indexer reload.
- **Schedule** — same form as the legacy `/schedule` page.
- **Jobs** — same content as the legacy `/health` page.

### Kill switches
- **Anthropic master** — `app_settings.anthropic.enabled`. When false, all Claude calls return 503 with a descriptive error.
- **TV-context vision** — `app_settings.tv_context.vision_enabled_this_month` boolean.
- **Per-loop** — every loop's `enabled` flag stored in `app_settings`. Disabled loops short-circuit on their next tick.

---

## Boards & Watchlist

Two parallel ticker lists. Consolidated UI under `/watchlist`.

- **Watchlist (roster)** — drives the daily scheduler. Operator-curated; symbols here get forecasts daily.
- **Boards** — casual / thematic lists ("AI infra", "rate-sensitive", "earnings this week"). One ticker can sit on the roster + N boards independently.

Both contribute to the **operator universe** (roster ∪ all boards) used by the ticker-whitelist for chart extraction, attention scoring, and the unknown-ticker review queue.

---

## Glossary (A–Z)

- **Actual** — the real OHLCV bar that lands after a prediction's target date passes.
- **Attention score** — see rx finance. Decay-weighted sum of recent TV-context items mentioning any ticker in the rec.
- **Axis (hypothesis)** — free-form bucket label (e.g. `liquidity`, `equity:AAPL`). Used for filtering, not validation.
- **Backfill** — regenerate a derived table (`prediction_points`, FTS5 index, evergreen flags) from canonical source after a schema change.
- **Baseline** — the close at the made-on date. Anchor for direction-correctness and predicted-move math.
- **Bar** — one OHLCV candle for one ticker, one interval, one timestamp.
- **Cadence** — the interval (1d, 1h, etc.). Two cadences are never averaged together.
- **Confirmed-at** — earnings date confirmed by an actual 8-K Item 2.02 filing (US only).
- **Drift alert** — `drift_alerts` row flagging `(ticker, horizon, model)` whose recent MAPE materially exceeded all-time MAPE. See **Drift**.
- **Eligible / ineligible** — whether a prediction task passed validation (asset class, history depth, supported interval). Ineligible tasks resolve immediately with a structured reason.
- **Evergreen** — vault node flag (NULL / 0 / 1). Evergreen nodes bypass decay (always weight 1.0); non-evergreen subject to per-author ranked decay.
- **Fan-out** — one analysis job spawns N tasks (`tickers × intervals × models`).
- **Forced decision** — see rx finance. Snoozed ≥ 2× → must disposition.
- **Forecast cell** — see Predictions. A By Horizon cell whose target hasn't passed yet.
- **FTS5** — SQLite full-text-search v5 virtual table. Backs the lexical leg of vault hybrid retrieval.
- **HypothesisTVContextLink** — pointer table (hypothesis_id × tv_context_item_id) with `stance` column.
- **Invalidator** — DSL spec on a hypothesis. Auto-flips status when triggered. See **Hypotheses**.
- **Job** — one `POST /v1/analysis/run`; spawns tasks, settles when all tasks resolve.
- **Manual close** — operator-driven hypothesis dismissal via `/cancel` route.
- **MOVE** — ICE BofA MOVE Index. Bond market's VIX. Surfaced on Macro → Stress panel.
- **n** — sample count. Cells / scores with `n < 4` are greyed-out as insufficient evidence.
- **Operator universe** — `roster ∪ all boards ∪ The Street tier-1/2 (last 4 snapshots)`. The whitelist used by chart-extractor + rx attention + ticker-review.
- **Outbox** — cross-laptop sync queue (Tailscale). Every CRUD on shared tables enqueues a row that the peer drains.
- **Pending run** — see Schedule.
- **Rec** (rx) — short for finance recommendation. Lives under `/motion/recs`.
- **Reciprocal rank fusion (RRF)** — score-blind merge of two ranked lists. Used by vault search to combine vector + lexical.
- **Regime** — see Macro Workbench. A persistent market state.
- **Settled cell** — a By Horizon cell whose target has passed and whose actual is cached.
- **Snooze** — push a rec out 1–7 days. Counted.
- **Stance** — TV-context link's directional flag on a hypothesis: `supports` / `challenges` / `context`.
- **Subjective fit (1–5)** — operator gut-check on an acted rec.
- **Task** — one cell of a fan-out: a single (ticker, interval, model) prediction request.
- **Ticker review queue** — surface for unknown tickers extracted from video + TV-context.
- **Universe** — see operator universe.
- **Watchlist** — see Boards & Watchlist.
- **Window** — see Accuracy. Rolling window for hit-rate / MAPE smoothing.
- **Yield curve** — Macro panel surfacing 2Y / 10Y / 30Y treasuries + 2s10s + 10y-3m spreads.

---

## Reading the colors at a glance

| View | 🟢 Green | 🟡 Yellow | 🔴 Red | ⚪ Grey |
|---|---|---|---|---|
| **By Horizon** Δ% | undershoot < −1% | (n/a) | overshoot > +1% | within ±1% |
| **Accuracy** | `hit ≥ 60% AND MAPE ≤ 2%` | in-between | `hit < 50% OR MAPE > 4%` | `n < 4` insufficient |
| **Signals (Motion)** | high-score, all rules passed | partial | rule failed | no opportunity |
| **Trades** | profitable | break-even ±1% | losing | open / pending |
| **rx status** | acted | snoozed | dismissed / forced | open (awaiting) |
| **Hypothesis status** | active | at-risk (drift-flagged) | invalidated | expired / cancelled |
| **Macro row** | within `directional.up` threshold | between thresholds | within `directional.down` threshold | no signal |

If a color surprises you, hover for the tooltip — it explains why.
