export type BackendId = 'laptop' | 'railway'

export interface AccuracyGridRow {
  ticker: string
  horizon_offset: number
  model_id: string
  interval: string
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
  // Per-task outcome buckets — populated by /v1/analysis/jobs list
  // endpoint; collapsed-row OutcomeBar reads these eagerly.
  done?: number
  ineligible?: number
  error?: number
  running?: number
  pending?: number
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

// ---------------------------------------------------------------------------
// Macro Workbench (M-1)
// ---------------------------------------------------------------------------

export interface MacroPoint {
  ts: string // ISO date (YYYY-MM-DD)
  value: number
}

export interface MacroSeriesResponse {
  symbol: string
  source: string | null
  points: MacroPoint[]
}

export interface MacroRatioResponse {
  numerator: string
  denominator: string
  points: MacroPoint[]
}

export interface MacroSpreadResponse {
  minuend: string
  subtrahend: string
  points: MacroPoint[]
}

export interface MacroRefreshResponse {
  rows_touched: number
  ok: number
  failed: number
  skipped: number
  failures: string[]
}

// ---------------------------------------------------------------------------
// Boards (UI calls them "Watchlists") — Phase MW-2
// ---------------------------------------------------------------------------

export interface BoardSummary {
  id: string
  name: string
  description: string | null
  ticker_count: number
  created_at: string
  updated_at: string
}

export interface BoardTickerOut {
  ticker: string
  notes: string | null
  added_at: string
  last_close: number | null
  last_close_at: string | null
  pct_1w: number | null
  quote_fetched_at: string | null
}

export interface BoardDetail extends BoardSummary {
  tickers: BoardTickerOut[]
}

export interface BoardsListResponse {
  items: BoardSummary[]
}

// ---------------------------------------------------------------------------
// Bulk quotes (last_close + pct_1w) — Phase MW-2/MW-3
// ---------------------------------------------------------------------------

export interface QuotePoint {
  symbol: string
  last_close: number | null
  last_close_at: string | null
  pct_1w: number | null
  quote_fetched_at: string | null
}

export interface QuotesResponse {
  items: QuotePoint[]
}

// ---------------------------------------------------------------------------
// Hypotheses — M-2
// ---------------------------------------------------------------------------

export type HypothesisStatus =
  | 'active'
  | 'expired'
  | 'invalidated'
  | 'cancelled'
  | 'manual_closed'

export type ClaimType = 'regime' | 'tactical' | 'single_name' | 'breakout'

export interface InvalidatorSpec {
  op:
    | 'ratio_below_sma'
    | 'series_above_threshold'
    | 'series_below_threshold'
    | 'series_change_pct'
    | 'manual'
  args: Record<string, unknown>
}

export interface HypothesisEvaluation {
  id: string
  evaluated_at: string
  status_before: HypothesisStatus
  status_after: HypothesisStatus
  reason: string
  invalidator_result: Record<string, unknown> | null
}

export interface Hypothesis {
  id: string
  slug: string
  title: string
  claim_type: ClaimType
  axis: string
  parent_id: string | null
  precondition_id: string | null
  primary_metric: string
  tracking_signal: string
  invalidator: InvalidatorSpec
  ttl_months: number
  created_at: string
  expires_at: string
  status: HypothesisStatus
  body_md: string | null
  recent_evaluations: HypothesisEvaluation[]
}

export interface HypothesisListResponse {
  items: Hypothesis[]
  count: number
}

export interface HypothesisSummary {
  active: number
  expired: number
  invalidated: number
  cancelled: number
  manual_closed: number
  at_risk: number
}

// ---------------------------------------------------------------------------
// Views — M-2
// ---------------------------------------------------------------------------

export interface ViewPanel {
  kind: 'ratio' | 'series' | 'spread' | 'hypothesis_filter'
  numerator?: string
  denominator?: string
  symbol?: string
  sma_days?: number
  threshold?: number
  axis?: string
}

export interface ViewSpec {
  id: string
  title: string
  default_axis: string | null
  panels: ViewPanel[]
  body: string | null
}

export interface ViewsResponse {
  items: ViewSpec[]
  count: number
}

// ---------------------------------------------------------------------------
// Research — M-2 Phase 3 / 3.7 (single-turn UI)
// ---------------------------------------------------------------------------

export interface EvidenceItem {
  vault_path: string
  title: string | null
  section: string | null
  text: string
  similarity: number
  decay_weight: number
  score: number
  published_at: string | null
  author: string | null
}

export interface MacroSnapshotItem {
  symbol: string
  latest: number
  latest_ts: string
}

export interface SourceContextItem {
  /** Vault path of the operator-authored `_index.md` vignette. */
  path: string
  title: string | null
  /** Markdown body, verbatim — no truncation by design. */
  body: string
  /** Evidence vault paths this vignette applies to (covered by ancestor walk). */
  applies_to: string[]
}

export interface ProposedAction {
  hypothesis_slug: string
  rationale: string
  proposed_invalidator: InvalidatorSpec
  evidence_paths?: string[]
  confidence: number
}

export interface AskRequest {
  query: string
  hypothesis_slugs?: string[]
  tickers?: string[]
  force_skip_context_gate?: boolean
  skill_slug?: string
}

export interface ResearchSkillInfo {
  slug: string
  title: string
  description: string
  tool: string | null
  default: boolean
}

export interface ResearchSkillsList {
  items: ResearchSkillInfo[]
  count: number
}

export interface TickerContextStatus {
  ticker: string
  available_count: number
  most_recent_at: string | null
  needs_context: boolean
}

export interface AskResponse {
  query_id: string
  answer_path: string | null
  verdict: string | null
  tokens_in: number
  tokens_out: number
  est_cost_usd: number
  proposed_action: ProposedAction | null
  status: 'pending' | 'approved' | 'dismissed' | 'error' | 'needs_context'
  evidence: EvidenceItem[]
  macro_state: MacroSnapshotItem[]
  source_context: SourceContextItem[]
  context_check?: TickerContextStatus[]
}

export interface ResearchQueryRead {
  id: string
  asked_at: string
  query: string
  hypothesis_ids: string[]
  answer_path: string | null
  verdict: string | null
  tokens_in: number | null
  tokens_out: number | null
  est_cost_usd: number | null
  status: 'pending' | 'approved' | 'dismissed' | 'error'
  approved_at: string | null
  proposed_action: ProposedAction | null
  evidence: EvidenceItem[]
  macro_state: MacroSnapshotItem[]
  source_context: SourceContextItem[]
  /** Composite ranking score (app/research/ranking.py). null on legacy rows. */
  score: number | null
  /** True when this query sits in the backlog (outside the visible top-5). */
  is_deferred: boolean
  /** Set when the retention sweep auto-aged this pending query into dismissed. */
  auto_aged_at: string | null
}

export interface ResearchQueriesList {
  items: ResearchQueryRead[]
  count: number
}

// ---------------------------------------------------------------------------
// TV Context — Phase 1-6 ingest layer for TradingView signals
// ---------------------------------------------------------------------------

export type TVContextKind = 'webhook' | 'screenshot' | 'note' | 'idea' | 'event'
export type TVContextStatus = 'active' | 'expired' | 'archived'

export interface TVContextItem {
  id: string
  kind: TVContextKind
  ticker: string | null
  source: string
  captured_at: string
  expires_at: string | null
  status: TVContextStatus
  payload: Record<string, unknown>
  tombstone: Record<string, unknown> | null
  vault_path: string | null
  heavy_blob_dropped: boolean
}

export interface TVContextIngestResult {
  item: TVContextItem | null
  deduped: boolean
  dedupe_count: number | null
}

export interface TVNoteIngest {
  ticker?: string | null
  body: string
  tags?: string[]
  expires_at?: string | null
}

export interface TVIdeaIngest {
  ticker?: string | null
  url: string
  summary?: string | null
  tags?: string[]
  expires_at?: string | null
}

export interface TVEventIngest {
  ticker?: string | null
  label: string
  event_date: string  // YYYY-MM-DD
  body?: string | null
  expires_at?: string | null
}

export interface TVVisionSpend {
  month: string  // YYYY-MM
  total_usd: number
  call_count: number
}

export interface TVContextNeededInfo {
  ticker: string
  available_count: number
  most_recent_at: string | null
  needs_context: boolean
}

// ---------------------------------------------------------------------------
// The Street — smart-money snapshot wrapper (Phase 2 IA reorg)
// ---------------------------------------------------------------------------

export interface StreetSnapshot {
  date: string
  writeup_dir: string
  data_dir: string
  vault_path: string
}

export interface StreetSnapshotsResponse {
  items: StreetSnapshot[]
  count: number
}

export interface StreetTickerRow {
  date: string
  channels: number
  total_signals: number
  billionaires: number
  trailblazers: number
  insiders: number
  politicians: number
  options_bullish: number
  etf: boolean
  notable: string
  writeup_dir: string
}

export interface StreetTickerResponse {
  ticker: string
  items: StreetTickerRow[]
  count: number
}

export interface StreetTierRow {
  ticker: string
  channels: number
  total_signals: number
  billionaires: number
  trailblazers: number
  insiders: number
  politicians: number
  options_bullish: number
  notable: string
}

export interface StreetTierResponse {
  tier: number
  snapshot_date: string | null
  items: StreetTierRow[]
  count: number
}

export interface StreetPoliticianRow {
  snapshot_date: string
  ticker: string
  company: string
  traded: string
  disclosed: string
  value_range: string
  fv: string
}

export interface StreetPoliticianResponse {
  politician: string
  items: StreetPoliticianRow[]
  count: number
}

export interface StreetDigestFundEntry {
  fund: string
  company: string
  status: string
}

export interface StreetDigestInsiderEntry {
  date: string
  company: string
  person: string
  title: string
  value: string
  shares: string
  price: string
  sign: string
}

export interface StreetDigestPoliticianEntry {
  traded: string
  disclosed: string
  company: string
  fv: string
  member: string
  party: string
  district: string
  committee: string
  value_range: string
}

export interface StreetDigestOptionsEntry {
  date: string
  company: string
  fv: string
  signal: string
  conviction: string
  contract: string
  premium: string
  ratio: string
}

export interface StreetDigestEntry {
  ticker: string
  company: string
  channel_count: number
  total_signals: number
  channels: {
    billionaires?: StreetDigestFundEntry[]
    trailblazers?: StreetDigestFundEntry[]
    insiders?: StreetDigestInsiderEntry[]
    politicians?: StreetDigestPoliticianEntry[]
    options_bullish?: StreetDigestOptionsEntry[]
  }
  markdown: string
}

export interface StreetDigestResponse {
  snapshot_date: string
  ticker: string
  found: boolean
  entry: StreetDigestEntry | null
}

// ---------------------------------------------------------------------------
// Vault proxy
// ---------------------------------------------------------------------------

export interface VaultSearchHit {
  /** Full vault-relative path of the chunk's parent file. */
  path: string
  /** Order of this chunk within the file (0-indexed). */
  ord: number
  /** Full chunk body. UI shows `excerpt_sentences` first; `text` is the
   *  expanded view. */
  text: string
  /** Section heading the chunk falls under, when the file has h2s. */
  section?: string | null
  /** Pre-computed extractive teaser — top 2 sentences from `text` ranked
   *  by relevance to the search query, restored to original order.
   *  See `tools/vault_indexer/excerpt.py`. */
  excerpt_sentences: string[]
  title?: string | null
  kind?: string | null
  author?: string | null
  published_at?: string | null
  horizon_months?: number | null
  tags?: string[] | null
  similarity: number
  decay_weight: number
  score: number
}

export interface VaultSearchResponse {
  query: string
  k: number
  results: VaultSearchHit[]
}

export interface VaultFolderContextItem {
  path: string
  body_md: string
  title?: string | null
}

export interface VaultFolderContextResponse {
  items: VaultFolderContextItem[]
}

export interface VaultNodeResponse {
  path: string
  title?: string | null
  body_md: string
  kind?: string | null
  author?: string | null
  published_at?: string | null
  tags?: string[]
}
