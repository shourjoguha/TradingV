export type BackendId = 'laptop' | 'railway'

export interface AccuracyGridRow {
  ticker: string
  horizon_offset: number
  model_id: string
  sample_count: number
  mape: number
  rmse: number
  hit_rate: number | null
  latest_eval: string | null
}

export interface AccuracyGridResponse {
  rows: AccuracyGridRow[]
  window_size: number
}

export interface AccuracyPairRow {
  prediction_id: string
  model_id: string
  made_on: string
  target_date: string
  predicted_close: number
  actual_close: number
  baseline_close: number | null
  error_pct: number
  abs_error_pct: number
  squared_error: number
  direction_correct: boolean | null
  evaluated_at: string
}

export interface AccuracyPairResponse {
  ticker: string
  horizon_offset: number
  rows: AccuracyPairRow[]
}

export interface DriftAlert {
  id: string
  ticker: string
  horizon_offset: number
  model_id: string
  recent_mape: number
  all_time_mape: number
  ratio: number
  flagged_at: string
  acknowledged_at: string | null
}

export interface Opportunity {
  id: string
  ticker: string
  kind: 'buy' | 'sell'
  generated_at: string
  source_prediction_id: string
  source_model_id: string
  rule_id: string
  rule_label: string
  predicted_move_pct: number
  confidence: number
  status: 'open' | 'acted' | 'expired' | 'dismissed'
  expires_at: string | null
  acted_at: string | null
  dismissed_at: string | null
  dismissed_reason: string | null
}

export interface QueueItem {
  id: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  source: 'manual' | 'schedule' | 'fallback'
  inputs: {
    tickers: string[]
    intervals: string[]
    model_ids?: string[] | null
    horizon_bars?: number | null
  }
  enqueued_at: string
  started_at: string | null
  finished_at: string | null
  job_id: string | null
  error: string | null
}

export interface QueueStats {
  pending: number
  running: number
  done: number
  failed: number
  cancelled: number
}

export interface Trade {
  id: string
  opportunity_id: string | null
  ticker: string
  side: 'buy' | 'sell'
  qty: number
  entry_price: number
  entry_at: string
  exit_price: number | null
  exit_at: string | null
  realized_pnl: number | null
  fees: number
  notes_md: string | null
}


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
