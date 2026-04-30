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
    long: 'Hard-asset vs paper-asset preference; reflation vs recession. Watches the relative move between commodities (gold, copper, oil) and equities. When this axis turns up, it suggests money is rotating out of paper claims into real assets — typically a regime that hurts long-duration tech and helps producers.',
  },
  growth_axis: {
    short: 'Breadth + risk appetite',
    long: 'Concentration vs participation. Captures whether a rally is broad-based (small-caps and equal-weight participating) or narrow (a handful of mega-caps doing all the work). Narrow rallies historically precede corrections — the breadth here is the canary.',
  },
  liquidity_axis: {
    short: 'Fed posture + curve shape',
    long: 'Tracks central-bank liquidity (Fed balance sheet), inflation expectations, the long end of the curve, and now the mortgage-spread financial-conditions stress signal. When liquidity is expanding, risk assets benefit; when it contracts, multiples compress.',
  },
  stress_axis: {
    short: 'Credit + dollar + panic',
    long: 'Credit-risk preference (HY vs IG), bond-vs-equity bid, dollar regime, and equity-volatility fear gauge. Multiple stress views in one place — when more than one of these turns red simultaneously, that\'s a real risk-off signal.',
  },
  inflation_regime_axis: {
    short: 'Stagflation / inflation cycle',
    long: 'Dedicated panel for tracking inflation-regime shifts. Real yields are the cleanest stagflation tell — when nominal yields rise but real yields don\'t, inflation expectations are running hot. Pair with PPI/CPI (cost-push leading consumer prices) and broad commodities to see if the move is structural or cyclical.',
  },

  // --- Inflation panel rows ---
  r_gold_spx: {
    short: 'Gold vs equity',
    long: 'Ratio of gold front-month futures to SPX. Rising = capital rotating from equities into hard assets, classic debasement / late-cycle / stagflation signal. Falling = risk-on, equity bid wins.',
    docHref: '/docs/metrics#predictions',
  },
  r_copper_gold: {
    short: 'Reflation vs recession',
    long: 'Copper rises with global growth; gold rises on fear / debasement. Rising ratio = reflation / growth bid; falling = recession / hard-asset hedge. Often leads the 10-year Treasury yield by weeks.',
  },
  r_oil_gold: {
    short: 'Energy-led vs monetary inflation',
    long: 'Distinguishes inflation driven by energy prices (rising ratio) from monetary debasement broadly (falling ratio while gold leads). Helps tell a stagflation story apart from a pure-debasement story.',
  },

  // --- Growth panel rows ---
  r_rsp_spy: {
    short: 'Breadth: equal-weight vs cap-weight',
    long: 'When RSP outperforms SPY, the average stock is participating. When SPY outperforms RSP, a handful of mega-caps are dragging the index. Narrow rallies are fragile — this is the cleanest single-line breadth proxy.',
  },
  r_iwm_spy: {
    short: 'Small-cap risk appetite',
    long: 'Russell 2000 small-caps vs S&P 500. Rising = animal spirits returning; small caps are sensitive to credit, growth, and risk preference. Falling = de-risking; investors retreat to safety + scale.',
  },
  r_eem_spy: {
    short: 'EM vs developed',
    long: 'Emerging-markets vs US large caps. Driven by USD strength (inverse), commodity cycles, and global growth. Multi-year regimes tend to swing — the LatAm / EM-leadership thesis lives here.',
  },

  // --- Liquidity panel rows ---
  r_walcl: {
    short: 'Fed balance sheet',
    long: 'Total assets on the Fed\'s balance sheet. Expanding = liquidity tailwind for risk assets; contracting = quantitative tightening, multiples compress. Slow-moving but the strongest single liquidity input.',
  },
  r_t10yie: {
    short: '10Y inflation expectations',
    long: 'Market-implied 10-year average inflation, derived from TIPS spreads. Rising = inflation expectations un-anchoring upward; falling = disinflation. Watch this with real yields for the cleanest regime read.',
  },
  r_wgs10y: {
    short: '10Y Treasury yield',
    long: 'Long-end nominal yield. Rising = either growth bid or inflation premium; falling = flight to safety or growth scare. Read alongside breakevens and real yields to know which.',
  },
  r_mortgage_spread: {
    short: 'Mortgage stress over Treasury',
    long: '30-year fixed-rate mortgage minus 10-year Treasury yield. Normally ~150-200bps. When this blows out, MBS investors are demanding risk premium beyond rates — financial-conditions tightening that the headline 10Y doesn\'t reveal. Stagflation\'s quiet killer because housing locks up first.',
  },

  // --- Stress panel rows ---
  r_hyg_lqd: {
    short: 'High-yield vs investment-grade',
    long: 'High-yield credit ETF vs investment-grade. When HY outperforms IG, credit is hungry for risk; when HY breaks down vs IG, default fears are creeping in. Often leads equity sell-offs by weeks.',
  },
  r_tlt_spy: {
    short: 'Bond bid vs equity bid',
    long: 'Long-duration Treasuries vs S&P 500. Rising = rotating into safety / disinflation expectations; falling = equity bid wins. The classic risk-on / risk-off see-saw.',
  },
  r_dxy: {
    short: 'US Dollar regime',
    long: 'Trade-weighted DXY index. Strong dollar pressures EM, commodities, and US multinational earnings. Multi-year regimes anchor everything else — the LatAm and BTC theses both depend on this rolling over.',
  },
  r_vix: {
    short: 'Equity panic gauge',
    long: 'CBOE Volatility Index, daily close. Spikes with sell-offs; quiet under 15, complacent under 12, panicked above 30. The single number that says "is the market pricing in risk?". Different from credit stress — VIX is equity panic, HYG/LQD is fixed-income panic.',
  },

  // --- Inflation regime panel rows (NEW for stagflation tracking) ---
  r_dfii10: {
    short: '10Y real yield',
    long: 'TIPS-implied 10-year real yield (nominal − inflation expectations). The single sharpest stagflation tell: when nominal yields rise but real yields fall, inflation expectations are running away. Negative real yields = financial repression / debasement environment, gold and commodities thrive.',
  },
  r_t5yie: {
    short: '5Y inflation expectations',
    long: 'Faster-moving cousin of T10YIE. The 5Y is more responsive to actual inflation prints; divergence between 5Y and 10Y breakevens means expectations are shifting at one horizon and not the other — important for distinguishing transitory from structural inflation.',
  },
  r_ppi_cpi: {
    short: 'Producer prices over consumer prices',
    long: 'Producer Price Index ÷ Consumer Price Index. PPI leads CPI by ~3-6 months because producers pass costs through to consumers. Rising ratio = cost-push inflation in the supply chain; corporate margins about to get squeezed. Best single "stagflation is in the pipeline" signal.',
  },
  r_dbc_spy: {
    short: 'Broad commodities vs equities',
    long: 'Commodities ETF (energy, ag, metals weighted) over SPY. Different from Gold/SPX in that it captures the energy + agricultural commodity story that drives real-economy inflation. When this rises, real assets are eating equity returns — the stagflation playbook in one line.',
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
