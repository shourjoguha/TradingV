/**
 * Single source of truth for in-app term definitions. Every <InfoBubble />
 * and <HoverTooltip term="..." /> reads from this registry. The Docs hub
 * (`/docs/metrics`) carries the long-form versions; this file is the
 * tooltip-sized companion that doesn't require a click.
 *
 * Keys are stable identifiers (snake_case). The `docHref` should match a
 * `rehype-slug`-generated anchor in `frontend/src/docs/metrics.md` so the
 * "Read more" link scrolls to the right section.
 */

export interface GlossaryEntry {
  short: string
  long: string
  docHref?: string
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  // --- Predictions ---
  delta_pct: {
    short: 'Δ% — predicted vs actual',
    long: '(predicted_close − actual_close) / actual_close × 100. Positive = prediction was above the actual (overshoot); negative = below (undershoot).',
    docHref: '/docs/metrics#%CE%B4-delta-percent--the-by-horizon-cell-value',
  },
  horizon: {
    short: 'How many bars ahead',
    long: 'Number of bars from the made-on day to the predicted target. T-1 = next bar, T-5 = five bars ahead. Stored as horizon_offset.',
    docHref: '/docs/metrics#horizon-t-n-nd-nh',
  },
  made_on: {
    short: 'Forecast generation date',
    long: 'The day the prediction was generated. A prediction made on Monday for T-1 targets Tuesday\'s bar.',
    docHref: '/docs/metrics#made-on-date',
  },
  target_date: {
    short: 'Day the prediction is for',
    long: 'The day the predicted bar covers. Used to pair against the eventually-published actual.',
    docHref: '/docs/metrics#target-date',
  },
  forecast_only: {
    short: 'Target hasn\'t passed yet',
    long: 'A forecast cell is one whose target date is still in the future — only the prediction exists, no actual yet. Shown italic with a → arrow on the By Horizon matrix.',
    docHref: '/docs/metrics#forecast-vs-settled',
  },

  // --- Accuracy ---
  hit_rate: {
    short: 'Directional accuracy',
    long: 'Fraction of predictions whose direction matched the actual move from baseline. Doesn\'t account for magnitude — a model can score high here while every individual call is far off.',
    docHref: '/docs/metrics#hit-rate-directional-accuracy',
  },
  mape: {
    short: 'Mean Absolute % Error',
    long: 'mean(|actual − predicted| / actual). The average size of a prediction miss, regardless of direction. Lower is better.',
    docHref: '/docs/metrics#mape--mean-absolute-percentage-error',
  },
  rmse: {
    short: 'Root Mean Squared Error',
    long: 'sqrt(mean((actual − predicted)^2)). The dollar-magnitude version of MAPE. Penalises big misses more harshly than small ones.',
    docHref: '/docs/metrics#rmse--root-mean-squared-error',
  },
  baseline_close: {
    short: 'Close on made-on day',
    long: 'The price on the made-on day (T0). Anchor for direction-correctness and predicted-move math.',
    docHref: '/docs/metrics#baseline-close',
  },
  sample_count: {
    short: '`n` — evaluated predictions',
    long: 'How many evaluated predictions are in this cell. Small n makes the rate noisy: with n=4, the only possible hit-rates are 0 / 25 / 50 / 75 / 100%. Cells with n < 4 are greyed out.',
    docHref: '/docs/metrics#n--sample-count',
  },
  composite_accuracy: {
    short: 'Why hit% AND MAPE',
    long: 'A model that always says "up" can score 100% hit rate on a steadily rising stock while still being economically useless because every individual call is far from the actual close. Pairing hit-rate with MAPE stops that lucky-but-wrong trap.',
    docHref: '/docs/metrics#why-both--and-the-lucky-but-wrong-trap',
  },

  // --- Drift ---
  drift_ratio: {
    short: 'recent / all-time MAPE',
    long: 'recent_30d_mape / all_time_mape. A drift alert is flagged when ratio ≥ 1.5 with both windows meeting minimum sample sizes.',
    docHref: '/docs/metrics#drift-ratio',
  },

  // --- Macro Workbench ---
  macro_ratio: {
    short: 'Numerator ÷ denominator',
    long: 'Two macro_series symbols divided on the same date. Twelve canonical ratios cover the v1 spec (e.g. GC=F/SPY, RSP/SPY, HYG/LQD). Computed at query time.',
    docHref: '/docs/metrics#predictions',
  },
  regime: {
    short: 'Multi-month market state',
    long: 'A market state that biases ratios and asset returns systematically over weeks-to-quarters (risk-on, debasement, recession). The Macro Workbench surfaces which regime the data is currently in.',
  },
  inflation_axis: {
    short: 'Hard vs paper assets',
    long: 'Hard-asset vs paper-asset preference; reflation vs recession. Headline ratios: Gold/SPX, Copper/Gold, Oil/Gold.',
  },
  growth_axis: {
    short: 'Breadth + risk appetite',
    long: 'Concentration vs participation. Headlines: Equal-weight/Cap-weight (RSP/SPY), Small/Large (IWM/SPY), EM/DM (EEM/SPY).',
  },
  liquidity_axis: {
    short: 'Fed posture + curve shape',
    long: 'Fed balance sheet, inflation expectations, yield curve shape. Headlines: WALCL, T10YIE, 10Y Treasury.',
  },
  stress_axis: {
    short: 'Credit + dollar regime',
    long: 'Credit-risk preference, bond-vs-equity bid, dollar regime. Headlines: HYG/LQD, TLT/SPY, DXY.',
  },

  // --- Opportunities + Trades ---
  predicted_move_pct: {
    short: 'Bullishness of a prediction',
    long: '(predicted_close − baseline_close) / baseline_close × 100. Positive = bullish call; negative = bearish.',
    docHref: '/docs/metrics#predicted-move-',
  },
  rule_confidence: {
    short: 'Historical hit rate',
    long: 'Snapshot of the rule\'s historical hit rate at the moment the opportunity was generated. Doesn\'t update afterwards.',
  },
  opportunity_status: {
    short: 'open / acted / dismissed / expired',
    long: 'Lifecycle: pending opportunities turn into acted (you traded it), dismissed (with a reason), or expired (passed without action).',
    docHref: '/docs/metrics#opportunities',
  },

  // --- Schedule ---
  next_run_at: {
    short: 'Next scheduled run',
    long: 'Recomputed on every config change AND at the end of every tick (against the freshly-loaded config) — so a PUT landing during execution is honored without losing today\'s slot.',
    docHref: '/docs/metrics#next_run_at',
  },
  pending_run: {
    short: 'Run is deferred',
    long: 'Set when a run is deferred — most commonly because the analysis queue was full (AtCapacity). The runner retries every retry_minutes until pending_run clears.',
    docHref: '/docs/metrics#pending_run',
  },
}

export function getGlossary(term: string): GlossaryEntry | undefined {
  return GLOSSARY[term]
}
