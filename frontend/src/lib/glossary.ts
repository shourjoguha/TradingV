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
  /**
   * Directional reading guide. Helps a reader with no context understand
   * which direction is bullish/bearish, and what level (if any) is the
   * "line in the sand". Renders in the InfoBubble popover when present.
   */
  directional?: {
    up: string
    down: string
    /** Optional "line in the sand" — a level / threshold that flips the regime. */
    threshold?: string
  }
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
    long: 'Ratio of gold front-month futures to SPX. Tracks whether capital is rotating into hard assets or paper claims.',
    directional: {
      up: 'Gold outperforming SPX — classic debasement / late-cycle / stagflation signal. Bullish hard assets and gold-correlated names; pressure on long-duration tech.',
      down: 'Equities winning vs gold — risk-on regime, growth bid intact. Bearish for the debasement thesis.',
      threshold: 'A multi-year trendline break upward marks a structural breakout (Costa\'s thesis). Below the 200-day SMA = regime fading.',
    },
  },
  r_copper_gold: {
    short: 'Reflation vs recession',
    long: 'Copper rises with global growth; gold rises on fear or debasement. Often leads the 10-year Treasury yield by several weeks.',
    directional: {
      up: 'Reflation / growth bid — supportive of cyclicals, industrials, EM. Higher rates likely to follow.',
      down: 'Recession-bid; gold winning means flight to hard-asset hedges. Watch for credit stress and yield-curve flattening to confirm.',
    },
  },
  r_oil_gold: {
    short: 'Energy-led vs monetary inflation',
    long: 'Distinguishes inflation driven by energy supply (oil leading) from broad monetary debasement (gold leading).',
    directional: {
      up: 'Energy-led inflation — bullish energy producers (XLE), pressure on consumers + transportation.',
      down: 'Monetary debasement dominating; oil glut or demand destruction. Often a recession tell when sustained.',
      threshold: 'Above ~0.04 suggests a real energy shock; below ~0.02 = oil weakness or excess supply.',
    },
  },

  // --- Growth panel rows ---
  r_rsp_spy: {
    short: 'Breadth: equal-weight vs cap-weight',
    long: 'Equal-weight S&P 500 (RSP) vs cap-weight (SPY). The cleanest single-line breadth proxy.',
    directional: {
      up: 'Average stock participating — healthy rally with broad participation.',
      down: 'Narrow rally; a handful of mega-caps carrying the index. Fragile — corrections often follow narrow leadership.',
      threshold: 'Cross below the 200-day SMA = breadth breakdown warning. Sustained underperformance for 60+ days is a serious risk-off signal.',
    },
  },
  r_iwm_spy: {
    short: 'Small-cap risk appetite',
    long: 'Russell 2000 small-caps vs S&P 500 large-caps. Small caps are credit-sensitive and growth-sensitive — they tell you about risk appetite below the surface.',
    directional: {
      up: 'Animal spirits returning; risk-on. Bullish for cyclicals, financials, regionals.',
      down: 'De-risking; investors retreating to scale and safety. Watch for credit-stress confirmation.',
    },
  },
  r_eem_spy: {
    short: 'EM vs developed',
    long: 'Emerging-markets vs US large caps. Driven inversely by USD strength, plus commodity cycles and global growth.',
    directional: {
      up: 'EM outperforming — usually means USD weakening and commodity cycle alive. Cross-confirms the LatAm thesis.',
      down: 'Flight to US; strong dollar regime pressures EM and commodity exporters.',
      threshold: 'Multi-year trendline breaks here are decade-defining regime shifts (e.g. 2002–2010 EM bull, 2011+ US dominance).',
    },
  },

  // --- Liquidity panel rows ---
  r_walcl: {
    short: 'Fed balance sheet',
    long: 'Total assets on the Fed\'s balance sheet. Slow-moving but the strongest single liquidity input.',
    directional: {
      up: 'Expanding (QE) — liquidity tailwind for risk assets. Multiples expand; long-duration growth + crypto benefit most.',
      down: 'Quantitative tightening — multiples compress, especially long-duration tech. Risk-off bias.',
      threshold: 'Year-over-year change matters more than level. Sharp contractions (>5% YoY) historically precede risk-off regimes.',
    },
  },
  r_t10yie: {
    short: '10Y inflation expectations',
    long: 'Market-implied 10-year average inflation, derived from TIPS spreads. The market\'s consensus on what inflation will average over the next decade.',
    directional: {
      up: 'Expectations un-anchoring upward — bullish gold / commodities, bearish bonds. Fed credibility under question.',
      down: 'Disinflation expectations — bond bid, growth-equity bid (multiples expand on lower discount rates).',
      threshold: 'Above 2.5% sustained = above Fed\'s tolerance ceiling, policy concern. Below 2.0% = transitory regime returning.',
    },
  },
  r_wgs10y: {
    short: '10Y Treasury yield',
    long: 'Long-end nominal yield. Read alongside breakevens and real yields to know which factor is driving moves.',
    directional: {
      up: 'Either growth bid or inflation premium rising. Bad for duration; good for banks and value cyclicals.',
      down: 'Flight to safety or growth scare. Bond bid; supports long-duration multiples.',
      threshold: '5% widely watched as a "new regime" line — sustained moves above suggest structural inflation regime.',
    },
  },
  r_mortgage_spread: {
    short: 'Mortgage stress over Treasury',
    long: '30-year fixed-rate mortgage minus 10-year Treasury yield. Normal range ~150-200bps. When this blows out, MBS investors are demanding risk premium beyond rates — financial-conditions tightening that the headline 10Y doesn\'t reveal.',
    directional: {
      up: 'Stress widening — housing market tightens, refis stop, consumer balance-sheet drag intensifies. A quiet stagflation killer.',
      down: 'Stress easing — refi activity picks up, housing-market liquidity returns.',
      threshold: 'Above 250bps sustained = stress regime (we\'re here). A sustained move back to ~180bps = normalisation.',
    },
  },

  // --- Stress panel rows ---
  r_hyg_lqd: {
    short: 'High-yield vs investment-grade',
    long: 'High-yield credit ETF vs investment-grade. Credit signals often lead equity sell-offs by weeks.',
    directional: {
      up: 'HY outperforming IG — credit hungry for risk; no default fears. Bullish for risk assets generally.',
      down: 'HY breaking down vs IG — default fears creeping in. Often the cleanest leading indicator of a coming equity correction.',
      threshold: 'Cross below 200-day SMA = canary chirping. Sustained breakdown for 60 days + rising VIX = serious risk-off setup.',
    },
  },
  r_tlt_spy: {
    short: 'Bond bid vs equity bid',
    long: 'Long-duration Treasuries vs S&P 500. The classic risk-on / risk-off see-saw.',
    directional: {
      up: 'Rotating into bonds — flight to safety or disinflation expectations driving duration bid.',
      down: 'Equity bid winning — risk-on. Watch for whether yields are rising too (growth bid) or stable (multiple expansion).',
    },
  },
  r_dxy: {
    short: 'US Dollar regime',
    long: 'Trade-weighted USD index. The most important macro variable — strong dollar pressures EM, commodities, multinational earnings.',
    directional: {
      up: 'USD strength — bearish for EM, gold, commodities, multinationals. Disinflationary for the rest of the world.',
      down: 'USD weakness — tailwind for hard assets, EM, multinational earnings. Confirms the LatAm and BTC theses.',
      threshold: '110+ sustained = pressure regime (multinationals warn). Sub-95 = clear weakness regime. ~100 is breakeven.',
    },
  },
  r_vix: {
    short: 'Equity panic gauge',
    long: 'CBOE Volatility Index, daily close. The single number that says "is the market pricing in risk?". Different from credit stress (HYG/LQD) — VIX is equity panic specifically.',
    directional: {
      up: 'Fear rising. Often a contrarian buy signal when sustained, but a confirmation of risk-off when paired with credit stress + breadth breakdown.',
      down: 'Calm or complacency. Below 12 = warning sign of fragility (the calm before storms).',
      threshold: '<12 complacent · 15-20 normal · 20-30 elevated · >30 panic. >40 is rare crisis territory.',
    },
  },

  // --- Inflation regime panel rows (NEW for stagflation tracking) ---
  r_dfii10: {
    short: '10Y real yield',
    long: 'TIPS-implied 10-year real yield (nominal − inflation expectations). The single sharpest stagflation tell.',
    directional: {
      up: 'Real yields rising — disinflationary / aggressive Fed. Tough for gold, duration, and the stagflation thesis.',
      down: 'Real yields falling or negative — debasement environment. Bullish gold, commodities, real assets.',
      threshold: 'Above 2.5% sustained = Volcker-style policy success (kills the stagflation thesis). Negative real yields = structural debasement regime.',
    },
  },
  r_t5yie: {
    short: '5Y inflation expectations',
    long: 'Faster-moving cousin of T10YIE. More responsive to actual inflation prints.',
    directional: {
      up: 'Near-term inflation expectations rising — supply-chain pressure or wage-price spiral. Divergence above T10YIE = market thinks inflation is transitory but elevated.',
      down: 'Cooling — disinflation regime returning.',
      threshold: 'Above 2.5% sustained = un-anchored expectations (Fed credibility risk). Below 2.0% = back to "transitory" regime.',
    },
  },
  r_ppi_cpi: {
    short: 'Producer prices over consumer prices',
    long: 'PPI leads CPI by ~3-6 months because producers eventually pass costs through. Best single "stagflation is in the pipeline" signal.',
    directional: {
      up: 'Cost-push inflation building in the supply chain. Corporate margins about to get squeezed; CPI prints likely to rise within 2 quarters.',
      down: 'Cost-push relief — input prices easing faster than output prices. Margin recovery story.',
      threshold: 'Rolling 6mo rate-of-change > 0 for 3+ consecutive months = pressure building. < 0 for 90 days = pressure dissipating, stagflation thesis weakens.',
    },
  },
  r_dbc_spy: {
    short: 'Broad commodities vs equities',
    long: 'Commodities ETF (energy, ag, metals weighted) over SPY. Different from Gold/SPX — captures the energy + agricultural story that drives real-economy inflation.',
    directional: {
      up: 'Real assets eating equity returns — stagflation playbook winning. Energy + materials sectors typically lead.',
      down: 'Equities winning — commodity cycle topping or disinflation regime.',
      threshold: 'Cross above 200-day SMA = durable trend up. Sustained for 12 months = structural commodity cycle (1970s, 2000-2008, possibly now).',
    },
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
