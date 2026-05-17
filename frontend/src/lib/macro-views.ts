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

export interface RegimePanel {
  title: string
  blurb: string
  /** Glossary term key for the panel-level InfoBubble (i) circle. */
  term?: string
  rows: RegimeRow[]
}

export const REGIME_PANELS: RegimePanel[] = [
  {
    title: 'Inflation',
    blurb: 'Hard-asset vs paper-asset preference. Reflation vs recession.',
    term: 'inflation_axis',
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
export const SECTOR_ETFS: Array<{ symbol: string; label: string }> = [
  { symbol: 'XLK', label: 'Tech' },
  { symbol: 'XLF', label: 'Financials' },
  { symbol: 'XLE', label: 'Energy' },
  { symbol: 'XLV', label: 'Health' },
  { symbol: 'XLI', label: 'Industrials' },
  { symbol: 'XLP', label: 'Staples' },
  { symbol: 'XLY', label: 'Discretionary' },
  { symbol: 'XLU', label: 'Utilities' },
  { symbol: 'XLB', label: 'Materials' },
]

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
