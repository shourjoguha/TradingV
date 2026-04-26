export type BackendId = 'laptop' | 'railway'

export interface BackendConfig {
  id: BackendId
  label: string
  baseUrl: string
  apiKey: string
}

export interface Schedule {
  enabled: boolean
  tz_name: string
  run_at_local: string
  intervals: string[]
  horizon_bars: number
  model_ids: string[]
  retry_minutes: number
  collect_actuals: boolean
  skip_weekends: boolean
  next_run_at: string | null
  last_run_status: string | null
  last_run_at: string | null
  last_run_error?: string | null
  pending_run?: boolean
  updated_at?: string
}

export type ScheduleUpdate = Partial<
  Omit<Schedule, 'next_run_at' | 'last_run_status' | 'last_run_at' | 'updated_at'>
>

export interface WatchlistItem {
  symbol: string
  added_at: string
  notes: string | null
}

export interface WatchlistResponse {
  entries: WatchlistItem[]
  count: number
  /** alias of entries — for page compat */
  items: WatchlistItem[]
  /** alias of count — for page compat */
  total: number
}

export interface PredictionRecord {
  made_on: string
  made_on_dow: number
  days_ago: number
  horizon_offset: number
  model_id: string
  interval: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
}

export interface OhlcvCell {
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface ByTargetResponse {
  ticker: string
  target_date: string
  interval: string
  fields: string[]
  actual: OhlcvCell | null
  predictions: PredictionRecord[]
}

export interface ByHorizonRow {
  ticker: string
  target_date: string
  made_on: string | null
  days_ago: number | null
  actual: OhlcvCell | null
  prediction: OhlcvCell | null
}

export interface ByHorizonResponse {
  target_date: string
  interval: string
  fields: string[]
  rows: ByHorizonRow[]
}

export type Labels = Record<string, unknown>

export interface Model {
  id: string
  [key: string]: unknown
}

export interface OhlcvBar {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
}

export interface OhlcvResponse {
  symbol: string
  interval: string
  count: number
  bars: OhlcvBar[]
}

export interface AnalysisJob {
  id: string
  status: string
  task_count?: number
  submitted_at: string
  finished_at?: string | null
  /** alias of submitted_at for page compat — populated by hooks */
  created_at: string
  /** alias of finished_at (or submitted_at) — populated by hooks */
  updated_at: string
  tickers: string[]
  intervals: string[]
  model_ids: string[]
  horizon_bars?: number
  tasks?: AnalysisTask[]
  result_json?: Record<string, unknown> & {
    forecast?: Array<Record<string, unknown>>
  }
}

/** Page-compat wrapper for AnalysisJob list endpoint (backend returns bare array). */
export interface AnalysisJobsResponse {
  items: AnalysisJob[]
  total: number
}

export interface AnalysisTask {
  id: string
  ticker: string
  interval: string
  model_id: string
  status: string
  error?: string
  result_json?: Record<string, unknown> & {
    forecast?: Array<Record<string, unknown>>
  }
}

export interface HealthResponse {
  status: string
}
