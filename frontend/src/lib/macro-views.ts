/**
 * Single source of truth for which ratios live in which regime panel +
 * the 9 sector ETFs. Editing this file = changing the Macro page UI.
 *
 * Synced with backend `app/macro/registry.yaml`. If you add a symbol
 * here, ensure it's also in the registry so refresh covers it.
 */

export type RegimeRow =
  | { id: string; label: string; numerator: string; denominator: string }
  | { id: string; label: string; symbol: string; source?: 'yfinance' | 'fred' }

export interface RegimePanel {
  title: string
  blurb: string
  rows: RegimeRow[]
}

export const REGIME_PANELS: RegimePanel[] = [
  {
    title: 'Inflation',
    blurb: 'Hard-asset vs paper-asset preference. Reflation vs recession.',
    rows: [
      { id: 'gold-spy',    label: 'Gold / SPX',     numerator: 'GC=F', denominator: 'SPY' },
      { id: 'copper-gold', label: 'Copper / Gold',  numerator: 'HG=F', denominator: 'GC=F' },
      { id: 'oil-gold',    label: 'Oil / Gold',     numerator: 'CL=F', denominator: 'GC=F' },
    ],
  },
  {
    title: 'Growth',
    blurb: 'Breadth + risk appetite. Concentration vs participation.',
    rows: [
      { id: 'rsp-spy', label: 'Equal-wt / Cap-wt', numerator: 'RSP', denominator: 'SPY' },
      { id: 'iwm-spy', label: 'Small / Large',     numerator: 'IWM', denominator: 'SPY' },
      { id: 'eem-spy', label: 'EM / DM',           numerator: 'EEM', denominator: 'SPY' },
    ],
  },
  {
    title: 'Liquidity',
    blurb: 'Fed posture + inflation expectations + curve shape.',
    rows: [
      { id: 'walcl',  label: 'Fed BS (WALCL)',   symbol: 'WALCL',  source: 'fred' },
      { id: 't10yie', label: '10Y inflation exp', symbol: 'T10YIE', source: 'fred' },
      { id: 'wgs10y', label: '10Y Treasury',     symbol: 'WGS10YR', source: 'fred' },
    ],
  },
  {
    title: 'Stress',
    blurb: 'Credit-risk preference + bond-vs-equity bid + dollar regime.',
    rows: [
      { id: 'hyg-lqd', label: 'HY / IG credit',  numerator: 'HYG', denominator: 'LQD' },
      { id: 'tlt-spy', label: 'Bonds / Equities', numerator: 'TLT', denominator: 'SPY' },
      { id: 'dxy',     label: 'US Dollar (DXY)',  symbol: 'DX-Y.NYB' },
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
