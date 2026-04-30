# Metrics & Definitions

Plain-language reference for every term, ratio, and color you see across the platform. Bookmark this page; click any heading on the left to jump.

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

We compute it but don't currently surface it on the heatmap (visible in the per-cell hover tooltip). RMSE penalises big misses more harshly than small ones.

### `n` — sample count
How many evaluated predictions are in this cell. Small `n` makes the rate noisy: with `n=4`, the only possible hit rates are `0%, 25%, 50%, 75%, 100%`.

We grey-out cells with `n < 4` to avoid misleading you with single-prediction noise. As your watchlist evaluates more predictions, `n` rises and the numbers stabilise.

### Window
The rolling window selector (`last 10 / 30 / 100 / 500`) limits how many of the most-recent evaluations contribute. Smaller windows track recent behavior; larger windows smooth out noise.

### Interval
`1d`, `1h`, etc. The bar cadence of the prediction. The toggle on the Accuracy page splits cadences so a 1h-cadence model isn't averaged with a 1d-cadence one.

---

## Drift

A change in a model's recent error pattern that suggests something has shifted (regime change, data quality issue, model staleness).

### Recent vs. all-time MAPE
The drift detector compares recent MAPE (last 30 days) against all-time MAPE for the same `(ticker, horizon, model)`. If recent is meaningfully worse, we flag.

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
Open drift alerts surface as a banner on the Accuracy page. "Ack" dismisses the current alert and unblocks future re-flags for the same pair.

---

## Opportunities

A daily list of predictions that survived a battery of hand-tuned rules and look actionable. Trades are tracked separately; opportunities are the *suggestion*, trades are the *commitment*.

### Rule
A boolean check on a prediction (e.g. "predicted close moves > 1% AND historical hit rate for this ticker × horizon ≥ 60%"). Each rule has a name and a known historical hit rate.

### Baseline close
The close on the made-on day. Anchors "did the prediction expect movement?" — without a baseline we can't tell direction.

### Predicted move %
```
predicted_move_pct = (predicted_close − baseline_close) / baseline_close × 100
```
Positive = bullish call. Negative = bearish.

### Weighted score
Each surviving rule contributes its historical hit rate to a composite score. A higher score means the rule combination has been more reliable historically.

```
score = sum( hit_rate_of_each_passing_rule )
```

### Generation
Run automatically after each schedule cycle, plus manually via `POST /v1/opportunities/generate`.

---

## Trades

Manually logged buy/sell entries. The platform doesn't execute trades — you do — but logging closes the loop so the platform can attribute realised P&L back to the rules that suggested the opportunity.

### Open vs. closed
- **Open** — entry recorded, no exit yet. Shows unrealised P&L.
- **Closed** — exit recorded. Realised P&L is final.

### Realised P&L
```
realised = (exit_price − entry_price) × size × side_sign
```
where `side_sign = +1` for long, `−1` for short.

### Per-rule attribution
Each closed trade is attributed back to the rules that fired on the opportunity that triggered the trade. Per-rule P&L tells you which rules actually made you money — not just which had high hit rates.

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

## Glossary (A–Z)

- **Actual** — the real OHLCV bar that lands after a prediction's target date passes.
- **Backfill** — regenerate `prediction_points` from `analysis_tasks.result_json`. Used after a schema change.
- **Baseline** — the close at the made-on date. Anchor for direction-correctness and predicted-move math.
- **Bar** — one OHLCV candle for one ticker, one interval, one timestamp.
- **Cadence** — the interval (1d, 1h, etc.). Two cadences are never averaged together.
- **Eligible / ineligible** — whether a prediction task passed validation (asset class, history depth, supported interval). Ineligible tasks resolve immediately with a structured reason.
- **Fan-out** — one analysis job spawns N tasks (`tickers × intervals × models`).
- **Forecast cell** — see Predictions. A cell where the target hasn't passed yet.
- **Job** — one `POST /v1/analysis/run`; spawns tasks, settles when all tasks resolve.
- **Outbox** — the cross-laptop sync queue (Tailscale). Every CRUD on shared tables enqueues a row that the peer drains.
- **Pending run** — see Schedule.
- **Settled cell** — a By Horizon cell whose target date has passed and whose actual is cached.
- **Task** — one cell of a fan-out: a single (ticker, interval, model) prediction request.
- **Watchlist** — the list of tickers that the daily run targets.
- **Window** — see Accuracy.

---

## Reading the colors at a glance

| View | 🟢 Green | 🟡 Yellow | 🔴 Red | ⚪ Grey |
|---|---|---|---|---|
| **By Horizon** Δ% | undershoot < −1% | (n/a) | overshoot > +1% | within ±1% |
| **Accuracy** | `hit ≥ 60% AND MAPE ≤ 2%` | in-between | `hit < 50% OR MAPE > 4%` | `n < 4` insufficient |
| **Opportunities** | high-score, all rules passed | partial | rule failed | no opportunity |
| **Trades** | profitable | break-even ±1% | losing | open / pending |

If a color surprises you, hover for the tooltip — it explains why.
