/**
 * Minimal demo API client. No auth, no backend toggle, no retry. Hits
 * the public read-only Railway demo at VITE_DEMO_API_URL.
 */
const BASE_URL =
  (import.meta.env.VITE_DEMO_API_URL as string | undefined) ??
  'https://tradingv-production.up.railway.app'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

// --- types ---------------------------------------------------------------

export interface Manifest {
  schema_version: number
  cutoff_date: string
  generated_at: string
  scrub_version: string
  note: string
}

export interface DriftAlert {
  id: string
  ticker: string
  horizon: string
  ratio: number
  ack: boolean
  created_at: string
  note?: string
}

export interface ResearchPending {
  id: string
  question: string
  status: string
  created_at: string
}

export interface FreshSignal {
  id: string
  ticker: string
  kind: string
  rule: string
  score: number
  horizon: string
  created_at: string
}

export interface Regime {
  label: string
  vix: number | null
  spy_pct_1w: number | null
}

export interface TodayPayload {
  drift_alerts: DriftAlert[]
  research_pending: ResearchPending[]
  fresh_signals: FreshSignal[]
  regime: Regime
  watchlist_delta: unknown[]
}

export interface HorizonRow {
  ticker: string
  predicted: number
  current: number
  delta_pct: number
  as_of: string
}

export interface HorizonGroup {
  horizon: string
  rows: HorizonRow[]
}

export interface PredictionsByHorizon {
  horizons: HorizonGroup[]
}

export interface AccuracyRow {
  horizon: string
  samples: number
  mape: number
  hit_rate: number
}

export interface AccuracyGrid {
  rows: AccuracyRow[]
}

export interface Opportunity {
  id: string
  ticker: string
  kind: string
  rule: string
  score: number
  horizon: string
  status: string
  created_at: string
}

export interface OpportunityList {
  items: Opportunity[]
}

export interface Trade {
  id: string
  ticker: string
  side: string
  entry_price: number
  exit_price: number
  pnl_pct: number
  rule_attribution: string
  opened_at: string
  closed_at: string
}

export interface TradeList {
  items: Trade[]
}

export interface AskAnswer {
  id: string
  title: string
  tab: string
  body: string
}

export interface AskResponse {
  match: 'exact' | 'fuzzy' | 'miss'
  answer_id: string | null
  answer: AskAnswer | null
  suggestions: { id: string; label: string }[]
}

// --- methods -------------------------------------------------------------

export const demoApi = {
  manifest: () => get<Manifest>('/v1/manifest'),
  today: () => get<TodayPayload>('/v1/today'),
  byHorizon: () => get<PredictionsByHorizon>('/v1/predictions/by-horizon'),
  accuracy: () => get<AccuracyGrid>('/v1/accuracy/grid'),
  opportunities: () => get<OpportunityList>('/v1/opportunities'),
  trades: () => get<TradeList>('/v1/trades'),
  ask: (q: string) => post<AskResponse>('/v1/ask', { q }),
}
