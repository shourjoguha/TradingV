/**
 * Single source of truth for which ratios live in which regime panel +
 * the 9 sector ETFs. Editing this file = changing the Macro page UI.
 *
 * Synced with backend `app/macro/registry.yaml`. If you add a symbol
 * here, ensure it's also in the registry so refresh covers it.
 */

export type RegimeRow =
  // Series — single symbol over time.
  | { id: string; label: string; symbol: string; source?: 'yfinance' | 'fred'; term?: string }
  // Ratio — numerator ÷ denominator.
  | { id: string; label: string; numerator: string; denominator: string; term?: string }
  // Spread — minuend − subtrahend (computed on backend via /v1/macro/spread).
  | { id: string; label: string; minuend: string; subtrahend: string; term?: string }

/**
 * Macro-panel identity (2026-05-17 color taxonomy). Each panel maps to one
 * of the six `identity-*` Tailwind tokens; rendered as a 4px left-bar on
 * the CardHeader to give the operator a pre-attentive regime classifier.
 * Yield-curve + Liquidity share `liquidity` because both encode rate-axis
 * context; Inflation regime shares `inflation` for the same reason.
 */
export type PanelIdentity =
  | 'inflation'
  | 'growth'
  | 'liquidity'
  | 'stress'
  | 'narrative'
  | 'ambient'

export interface RegimePanel {
  title: string
  blurb: string
  /** Glossary term key for the panel-level InfoBubble (i) circle. */
  term?: string
  /** Identity color family — drives the header left-bar tint. */
  identity: PanelIdentity
  rows: RegimeRow[]
}

export const REGIME_PANELS: RegimePanel[] = [
  {
    title: 'Inflation',
    blurb: 'Hard-asset vs paper-asset preference. Reflation vs recession.',
    term: 'inflation_axis',
    identity: 'inflation',
    rows: [
      { id: 'gold-spy',    label: 'Gold / SPX',     numerator: 'GC=F', denominator: 'SPY', term: 'r_gold_spx' },
      { id: 'copper-gold', label: 'Copper / Gold',  numerator: 'HG=F', denominator: 'GC=F', term: 'r_copper_gold' },
      { id: 'oil-gold',    label: 'Oil / Gold',     numerator: 'CL=F', denominator: 'GC=F', term: 'r_oil_gold' },
    ],
  },
  {
    title: 'Growth',
    blurb: 'Breadth + risk appetite. Concentration vs participation.',
    term: 'growth_axis',
    identity: 'growth',
    rows: [
      { id: 'rsp-spy', label: 'Equal-wt / Cap-wt', numerator: 'RSP', denominator: 'SPY', term: 'r_rsp_spy' },
      { id: 'iwm-spy', label: 'Small / Large',     numerator: 'IWM', denominator: 'SPY', term: 'r_iwm_spy' },
      { id: 'eem-spy', label: 'EM / DM',           numerator: 'EEM', denominator: 'SPY', term: 'r_eem_spy' },
    ],
  },
  {
    title: 'Liquidity',
    blurb: 'Fed posture + curve shape + financial-conditions stress.',
    term: 'liquidity_axis',
    identity: 'liquidity',
    rows: [
      { id: 'walcl',  label: 'Fed BS (WALCL)',    symbol: 'WALCL',   source: 'fred',     term: 'r_walcl' },
      { id: 't10yie', label: '10Y inflation exp', symbol: 'T10YIE',  source: 'fred',     term: 'r_t10yie' },
      { id: 'wgs10y', label: '10Y Treasury',      symbol: 'WGS10YR', source: 'fred',     term: 'r_wgs10y' },
      { id: 'mort-spread', label: '30Y mortgage − 10Y', minuend: 'MORTGAGE30US', subtrahend: 'WGS10YR', term: 'r_mortgage_spread' },
    ],
  },
  {
    title: 'Stress',
    blurb: 'Credit-risk preference + bond-vs-equity bid + dollar regime + equity panic.',
    term: 'stress_axis',
    identity: 'stress',
    rows: [
      { id: 'hyg-lqd', label: 'HY / IG credit',   numerator: 'HYG', denominator: 'LQD',   term: 'r_hyg_lqd' },
      { id: 'tlt-spy', label: 'Bonds / Equities', numerator: 'TLT', denominator: 'SPY',   term: 'r_tlt_spy' },
      { id: 'dxy',     label: 'US Dollar (DXY)',  symbol: 'DX-Y.NYB',                     term: 'r_dxy' },
      { id: 'vix',     label: 'VIX (equity vol)', symbol: '^VIX',                         term: 'r_vix' },
      { id: 'move',    label: 'MOVE (bond vol)',  symbol: '^MOVE',                        term: 'r_move' },
    ],
  },
  {
    title: 'Inflation regime',
    blurb: 'Stagflation / inflation-cycle tracking. Real yields, breakevens, producer-vs-consumer prices, broad commodities.',
    term: 'inflation_regime_axis',
    identity: 'inflation',
    rows: [
      { id: 'dfii10',  label: 'Real 10Y yield',     symbol: 'DFII10',  source: 'fred',                   term: 'r_dfii10' },
      { id: 't5yie',   label: '5Y breakevens',      symbol: 'T5YIE',   source: 'fred',                   term: 'r_t5yie' },
      { id: 'ppi-cpi', label: 'PPI / CPI',          numerator: 'PPIACO', denominator: 'CPIAUCSL',        term: 'r_ppi_cpi' },
      { id: 'dbc-spy', label: 'Commodities / SPY',  numerator: 'DBC', denominator: 'SPY',                term: 'r_dbc_spy' },
    ],
  },
  {
    // Added 2026-05-17 per vault-audit of fx-evolution-daily + click-capital
    // transcripts. Operator's video diet repeatedly references curve shape +
    // long-end yields as leading regime signals. Five rows: three single-rate
    // series (2y/10y/30y) + two spreads (recession indicators).
    title: 'Yield curve',
    blurb: 'US Treasury curve shape + recession-signal spreads. 30Y "all-important 5%" + 2s10s + 10y-3m (NY Fed model).',
    term: 'yield_curve_axis',
    identity: 'liquidity',
    rows: [
      { id: 'wgs2y',     label: '2Y Treasury',     symbol: 'WGS2YR',  source: 'fred', term: 'r_wgs2y' },
      { id: 'wgs10y-yc', label: '10Y Treasury',    symbol: 'WGS10YR', source: 'fred', term: 'r_wgs10y' },
      { id: 'wgs30y',    label: '30Y Treasury',    symbol: 'WGS30YR', source: 'fred', term: 'r_wgs30y' },
      { id: 't10y2y',    label: '10Y − 2Y spread', symbol: 'T10Y2Y',  source: 'fred', term: 'r_t10y2y' },
      { id: 't10y3m',    label: '10Y − 3M spread', symbol: 'T10Y3M',  source: 'fred', term: 'r_t10y3m' },
    ],
  },
]

// 9-cell sector strip: each cell = sector ETF / SPY
// `defensive` flag drives the "defensive crowding" cue on the RS Leadership
// Ladder (Sectors sub-tab): when 2+ defensives crowd the top-3 RS rank, the
// page receives a subtle stress-tinted background — operator's native
// "defensives rotating in" signal made visible. See
// `lib/sector-strength.ts:defensiveCrowding`.
export interface SectorEtf {
  symbol: string
  label: string
  /** Defensive sectors per Fidelity/SSGA business-cycle taxonomy. */
  defensive: boolean
}

export const SECTOR_ETFS: SectorEtf[] = [
  { symbol: 'XLK', label: 'Tech',          defensive: false },
  { symbol: 'XLF', label: 'Financials',    defensive: false },
  { symbol: 'XLE', label: 'Energy',        defensive: false },
  { symbol: 'XLV', label: 'Health',        defensive: true  },
  { symbol: 'XLI', label: 'Industrials',   defensive: false },
  { symbol: 'XLP', label: 'Staples',       defensive: true  },
  { symbol: 'XLY', label: 'Discretionary', defensive: false },
  { symbol: 'XLU', label: 'Utilities',     defensive: true  },
  { symbol: 'XLB', label: 'Materials',     defensive: false },
]

/**
 * Per-sector identity color for the ladder's 4px left-bar. Maps to the
 * shipped `identity-*` Tailwind palette (2026-05-17 color taxonomy) by
 * intent — defensives borrow ambient/narrative steel-plum tones, cyclicals
 * borrow inflation/growth/stress, etc. Keeps the ladder's 9 cards visually
 * distinct without inventing a 10th palette family.
 */
export const SECTOR_IDENTITY_BG: Record<string, string> = {
  XLK: 'bg-identity-liquidity',  // Tech — slate-blue, rate-sensitive growth
  XLF: 'bg-identity-narrative',  // Financials — plum, story-driven
  XLE: 'bg-identity-inflation',  // Energy — ochre, hard-asset
  XLV: 'bg-identity-growth',     // Health — forest-teal, defensive-growth
  XLI: 'bg-identity-stress',     // Industrials — brick, cyclical
  XLP: 'bg-identity-ambient',    // Staples — steel, ambient defense
  XLY: 'bg-identity-stress',     // Discretionary — brick (paired w/ Industrials, both pro-cyclical)
  XLU: 'bg-identity-ambient',    // Utilities — steel, ambient defense
  XLB: 'bg-identity-inflation',  // Materials — ochre, hard-asset
}

/**
 * Hex-literal counterpart to `SECTOR_IDENTITY_BG` for SVG fill / stroke
 * (Tailwind class strings don't work inside `<svg>`). Kept in sync — if
 * you change one, change both. Values come from the
 * `colors.identity.*` block in `tailwind.config.js`.
 */
export const SECTOR_IDENTITY_HEX: Record<string, string> = {
  XLK: '#4A6FA5',  // identity-liquidity
  XLF: '#7A5AA8',  // identity-narrative
  XLE: '#C58A3D',  // identity-inflation
  XLV: '#3F7A6E',  // identity-growth
  XLI: '#B0533C',  // identity-stress
  XLP: '#5C7A8C',  // identity-ambient
  XLY: '#B0533C',  // identity-stress
  XLU: '#5C7A8C',  // identity-ambient
  XLB: '#C58A3D',  // identity-inflation
}

// RS Leadership Ladder math constants (Sectors sub-tab, 2026-05-17).
// 252 ≈ 1 trading year for the indexing base; 126 ≈ 6 months for z-score
// shape; 14 trading days ≈ 3 calendar weeks for short-term momentum.
// Conventional lookbacks — operator can sanity-check by eye.
export const RS_LOOKBACK_BASE = 252
export const RS_ZSCORE_WINDOW = 126
export const RS_MOMENTUM_WINDOW = 14
/** Below this absolute momentum value, the chevron renders neutral (→). */
export const RS_MOMENTUM_THRESHOLD = 0.005

// Default zoom for both sparklines and focused charts.
export const DEFAULT_SINCE_YEARS = 5

export const TIME_RANGE_OPTIONS = [
  { id: '1y',  label: '1Y',  years: 1 },
  { id: '3y',  label: '3Y',  years: 3 },
  { id: '5y',  label: '5Y',  years: 5 },
  { id: '10y', label: '10Y', years: 10 },
  { id: 'max', label: 'Max', years: 50 },
] as const

export function sinceFromYears(years: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

// Type guards.
export function isRatioRow(r: RegimeRow): r is Extract<RegimeRow, { numerator: string }> {
  return 'numerator' in r
}
export function isSpreadRow(r: RegimeRow): r is Extract<RegimeRow, { minuend: string }> {
  return 'minuend' in r
}
export function isSeriesRow(r: RegimeRow): r is Extract<RegimeRow, { symbol: string }> {
  return 'symbol' in r
}

// Compact subtitle showing the underlying symbols. Reused by RegimePanel
// + Dashboard tile.
export function rowSubtitle(r: RegimeRow): string {
  if (isRatioRow(r)) return `${r.numerator} ÷ ${r.denominator}`
  if (isSpreadRow(r)) return `${r.minuend} − ${r.subtrahend}`
  return r.symbol
}
