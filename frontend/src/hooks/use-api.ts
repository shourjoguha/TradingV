import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, healthCheck } from '../lib/api'
import { useBackend } from './use-backend'
import type {
  BackendId,
  Schedule,
  ScheduleUpdate,
  WatchlistResponse,
  WatchlistItem,
  Labels,
  Model,
  ByTargetResponse,
  ByHorizonResponse,
  OhlcvResponse,
  OhlcvBar,
  AnalysisJob,
  AnalysisJobsResponse,
  AccuracyGridResponse,
  AccuracyPairResponse,
  DriftAlert,
  Opportunity,
  Trade,
  QueueItem,
  QueueStats,
  MacroSeriesResponse,
  MacroRatioResponse,
  MacroRefreshResponse,
  MacroSpreadResponse,
  BoardSummary,
  BoardDetail,
  BoardsListResponse,
  Hypothesis,
  HypothesisListResponse,
  HypothesisSummary,
  HypothesisStatus,
  ClaimType,
  InvalidatorSpec,
  ViewsResponse,
  QuotesResponse,
  AskRequest,
  AskResponse,
  ResearchQueriesList,
  ResearchQueryRead,
  ResearchSkillsList,
  TVContextItem,
  TVContextIngestResult,
  TVNoteIngest,
  TVIdeaIngest,
  TVEventIngest,
  TVVisionSpend,
  StreetSnapshotsResponse,
  StreetTickerResponse,
  StreetTierResponse,
  StreetPoliticianResponse,
  StreetDigestResponse,
  VaultSearchResponse,
  VaultFolderContextResponse,
  VaultNodeResponse,
} from '../lib/types'
import { toast } from 'sonner'

export function useHealth() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['health', backendId],
    queryFn: () => healthCheck(backendId),
    refetchInterval: 30000,
  })
}

export function useSchedule() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['schedule', backendId],
    queryFn: () => apiFetch<Schedule>('/v1/schedule', { backendId }),
    refetchInterval: 30000,
  })
}

export function useUpdateSchedule() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ScheduleUpdate) =>
      apiFetch<Schedule>('/v1/schedule', { method: 'PUT', body: data, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule', backendId] })
      toast.success('Schedule updated')
    },
    onError: (err: any) => toast.error(`Update failed: ${err.detail || err.message}`),
  })
}

export function useFireNow() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch('/v1/schedule/fire-now', { method: 'POST', backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule', backendId] })
      qc.invalidateQueries({ queryKey: ['analysis-jobs', backendId] })
      toast.success('Job fired')
    },
    onError: (err: any) => toast.error(`Fire failed: ${err.detail || err.message}`),
  })
}

export function useWatchlist(params?: { limit?: number; offset?: number; labels?: string }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['watchlist', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.limit) s.set('limit', String(params.limit))
      if (params?.offset) s.set('offset', String(params.offset))
      if (params?.labels) s.set('labels', params.labels)
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<{ entries: any[]; count: number }>(`/v1/watchlist${qs}`, { backendId }).then(
        (r): WatchlistResponse => ({
          entries: r.entries,
          count: r.count,
          items: r.entries,
          total: r.count,
        }),
      )
    },
    staleTime: 60000,
  })
}

export function useAddTicker() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { symbol: string; notes?: string }) =>
      apiFetch<WatchlistItem>('/v1/watchlist', { method: 'POST', body: data, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', backendId] })
      toast.success('Ticker added')
    },
    onError: (err: any) => toast.error(`Add failed: ${err.detail || err.message}`),
  })
}

export function useBulkAddTickers() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { symbols: string[] }) =>
      apiFetch<{ added: number } | unknown>('/v1/watchlist/bulk', {
        method: 'POST', body: data, backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', backendId] })
      toast.success('Bulk add complete')
    },
    onError: (err: any) => toast.error(`Bulk add failed: ${err.detail || err.message}`),
  })
}

export function useDeleteTicker() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (symbol: string) =>
      apiFetch(`/v1/watchlist/${symbol}`, { method: 'DELETE', backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', backendId] })
      toast.success('Ticker removed')
    },
    onError: (err: any) => toast.error(`Remove failed: ${err.detail || err.message}`),
  })
}

export function useTickerLabels(symbol: string) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['labels', backendId, symbol],
    queryFn: () => apiFetch<Labels>(`/v1/tickers/${symbol}/labels`, { backendId }),
    staleTime: 60000,
    enabled: !!symbol,
  })
}

export function useUpdateTickerLabels(symbol: string) {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (labels: Labels) =>
      apiFetch<Labels>(`/v1/tickers/${symbol}/labels`, {
        method: 'PUT', body: { labels }, backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['labels', backendId, symbol] })
      qc.invalidateQueries({ queryKey: ['watchlist', backendId] })
      toast.success('Labels updated')
    },
    onError: (err: any) => toast.error(`Update labels failed: ${err.detail || err.message}`),
  })
}

export function useDeleteTickerLabel(symbol: string) {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) =>
      apiFetch(`/v1/tickers/${symbol}/labels/${key}`, { method: 'DELETE', backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['labels', backendId, symbol] })
      toast.success('Label removed')
    },
    onError: (err: any) => toast.error(`Remove label failed: ${err.detail || err.message}`),
  })
}

export function useModels() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['models', backendId],
    queryFn: () => apiFetch<Model[]>('/v1/models', { backendId }),
    staleTime: 5 * 60000,
  })
}

export function usePredictionsByTarget(params: {
  ticker?: string
  target_date?: string
  interval?: string
  model_id?: string
  fields?: string
  made_on_dow?: string
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['predictions-target', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => { if (v) s.set(k, v) })
      return apiFetch<ByTargetResponse>(`/v1/predictions/by-target?${s}`, { backendId })
    },
    staleTime: 60000,
    enabled: !!params.ticker && !!params.target_date,
  })
}

export function usePredictionsByHorizon(params: {
  target_date?: string
  horizons?: string
  tickers?: string
  interval?: string
  model_id?: string
  fields?: string
  made_on_dow?: string
  mode?: 'target' | 'anchor'
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['predictions-horizon', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => { if (v) s.set(k, v) })
      return apiFetch<ByHorizonResponse>(`/v1/predictions/by-horizon?${s}`, { backendId })
    },
    staleTime: 60000,
    enabled: !!params.target_date && !!params.horizons && !!params.tickers,
  })
}

export function useOhlcv(params: { symbol?: string; interval?: string; limit?: number }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['ohlcv', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams({
        symbol: params.symbol!,
        interval: params.interval!,
        refresh: 'false',
      })
      if (params.limit) s.set('limit', String(params.limit))
      return apiFetch<OhlcvResponse>(`/v1/ohlcv?${s}`, { backendId }).then((r) =>
        r.bars.map((b) => ({ ...b, time: (b.ts ?? '').slice(0, 10) })) as Array<OhlcvBar & { time: string }>,
      )
    },
    staleTime: 60000,
    enabled: !!params.symbol && !!params.interval,
  })
}

export function useAnalysisJobs(params?: { limit?: number; offset?: number }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['analysis-jobs', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.limit) s.set('limit', String(params.limit))
      if (params?.offset) s.set('offset', String(params.offset))
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<AnalysisJob[]>(`/v1/analysis/jobs${qs}`, { backendId }).then(
        (arr): AnalysisJobsResponse => ({
          items: arr.map((j) => ({
            ...j,
            created_at: j.submitted_at,
            updated_at: j.finished_at ?? j.submitted_at,
            tickers: j.tickers ?? [],
            intervals: j.intervals ?? [],
            model_ids: j.model_ids ?? [],
          })),
          total: arr.length,
        }),
      )
    },
    refetchInterval: 30000,
  })
}

export function useAnalysisJob(jobId: string) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['analysis-job', backendId, jobId],
    queryFn: () => apiFetch<AnalysisJob>(`/v1/analysis/jobs/${jobId}`, { backendId }).then((j) => ({
      ...j,
      created_at: j.submitted_at,
      updated_at: j.finished_at ?? j.submitted_at,
      tickers: j.tickers ?? [],
      intervals: j.intervals ?? [],
      model_ids: j.model_ids ?? [],
    })),
    enabled: !!jobId,
  })
}

export function useAccuracyGrid(params?: {
  tickers?: string
  horizons?: string
  model_id?: string
  interval?: string
  last_n?: number
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['accuracy-grid', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.tickers) s.set('tickers', params.tickers)
      if (params?.horizons) s.set('horizons', params.horizons)
      if (params?.model_id) s.set('model_id', params.model_id)
      if (params?.interval) s.set('interval', params.interval)
      if (params?.last_n) s.set('last_n', String(params.last_n))
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<AccuracyGridResponse>(`/v1/accuracy/grid${qs}`, { backendId })
    },
    refetchInterval: 60000,
  })
}

export function useAccuracyPair(params: {
  ticker?: string
  horizon_offset?: number
  model_id?: string
  limit?: number
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['accuracy-pair', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      s.set('ticker', params.ticker!)
      s.set('horizon_offset', String(params.horizon_offset!))
      if (params.model_id) s.set('model_id', params.model_id)
      if (params.limit) s.set('limit', String(params.limit))
      return apiFetch<AccuracyPairResponse>(`/v1/accuracy/pair?${s}`, { backendId })
    },
    enabled: !!params.ticker && !!params.horizon_offset,
  })
}

export function useEvaluateAccuracy() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch('/v1/accuracy/evaluate', { method: 'POST', backendId }),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['accuracy-grid', backendId] })
      qc.invalidateQueries({ queryKey: ['drift-alerts', backendId] })
      toast.success(`Evaluated ${data.evaluated ?? 0} (skipped ${data.skipped_no_actual ?? 0} no-actual)`)
    },
    onError: (err: any) => toast.error(`Evaluate failed: ${err.detail || err.message}`),
  })
}

export function useDriftAlerts() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['drift-alerts', backendId],
    queryFn: () => apiFetch<{ alerts: DriftAlert[] }>('/v1/accuracy/drift', { backendId }),
    refetchInterval: 5 * 60000,
  })
}

export function useAckDriftAlert() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/accuracy/drift/${id}/ack`, { method: 'POST', backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['drift-alerts', backendId] })
      toast.success('Drift alert acknowledged')
    },
  })
}

export function useOpportunities(params?: {
  status?: string
  ticker?: string
  limit?: number
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['opportunities', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.status) s.set('status', params.status)
      if (params?.ticker) s.set('ticker', params.ticker)
      if (params?.limit) s.set('limit', String(params.limit))
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<{ items: Opportunity[]; count: number }>(`/v1/opportunities${qs}`, { backendId })
    },
    // Throttling fix: drop the always-on 60s poll. Pages that explicitly
    // need fresh data poll on focus or invalidate after a mutation; the
    // Today + TickerHub views rely on the staleTime cache, not a tick.
    staleTime: 60_000,
  })
}

export function useUpdateOpportunity() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { id: string; status: 'acted' | 'dismissed'; reason?: string }) =>
      apiFetch(`/v1/opportunities/${data.id}`, {
        method: 'PATCH',
        body: { status: data.status, dismissed_reason: data.reason },
        backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['opportunities', backendId] })
      toast.success('Opportunity updated')
    },
    onError: (err: any) => toast.error(`Update failed: ${err.detail || err.message}`),
  })
}

export function useTrades(params?: { limit?: number; ticker?: string }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['trades', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.limit) s.set('limit', String(params.limit))
      if (params?.ticker) s.set('ticker', params.ticker)
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<{ items: Trade[]; count: number; pnl_summary: any }>(`/v1/trades${qs}`, { backendId })
    },
    // Manual journal — only changes on operator mutation. Cache is fine.
    staleTime: 60_000,
  })
}

export function useCreateTrade() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Trade>) =>
      apiFetch<Trade>('/v1/trades', { method: 'POST', body: data, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trades', backendId] })
      toast.success('Trade logged')
    },
    onError: (err: any) => toast.error(`Log trade failed: ${err.detail || err.message}`),
  })
}

export function useUpdateTrade() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Trade> & { id: string }) =>
      apiFetch<Trade>(`/v1/trades/${data.id}`, { method: 'PATCH', body: data, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trades', backendId] })
      toast.success('Trade updated')
    },
    onError: (err: any) => toast.error(`Update trade failed: ${err.detail || err.message}`),
  })
}

// Tier-1 queue hooks ────────────────────────────────────────────────

export function useQueue(params?: { status?: string; limit?: number }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['queue', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.status) s.set('status', params.status)
      if (params?.limit) s.set('limit', String(params.limit))
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<{ items: QueueItem[]; count: number }>(
        `/v1/analysis/queue${qs}`,
        { backendId },
      )
    },
    refetchInterval: 5000,
  })
}

export function useQueueStats() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['queue-stats', backendId],
    queryFn: () => apiFetch<QueueStats>('/v1/analysis/queue/stats', { backendId }),
    refetchInterval: 5000,
  })
}

export function useQueueItem(queueId: string | null) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['queue-item', backendId, queueId],
    queryFn: () => apiFetch<QueueItem>(`/v1/analysis/queue/${queueId}`, { backendId }),
    enabled: !!queueId,
    // Stop polling when terminal. TanStack returns the data so we can
    // peek at it and decide whether to keep polling.
    refetchInterval: (query) => {
      const data = query.state.data as QueueItem | undefined
      if (!data) return 2000
      if (['done', 'failed', 'cancelled'].includes(data.status)) return false
      return 2000
    },
  })
}

export function useCancelQueueItem() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (queueId: string) =>
      apiFetch(`/v1/analysis/queue/${queueId}`, { method: 'DELETE', backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['queue', backendId] })
      qc.invalidateQueries({ queryKey: ['queue-stats', backendId] })
      toast.success('Cancelled')
    },
    onError: (err: any) => toast.error(`Cancel failed: ${err.detail || err.message}`),
  })
}

export function useRunAnalysis() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      tickers: string[]; intervals: string[]; model_ids?: string[]; horizon_bars?: number
    }) =>
      apiFetch<{ queue_id: string; status: string; job_id: string | null }>(
        '/v1/analysis/run',
        { method: 'POST', body: data, backendId },
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['queue', backendId] })
      qc.invalidateQueries({ queryKey: ['queue-stats', backendId] })
      qc.invalidateQueries({ queryKey: ['analysis-jobs', backendId] })
      toast.success(`Queued: ${data.queue_id.slice(0, 8)}…`, {
        description: 'Worker will pick this up shortly. Watch the queue widget on the Dashboard.',
      })
    },
    onError: (err: any) => toast.error(`Run failed: ${err.detail || err.message}`),
  })
}

// ---------------------------------------------------------------------------
// Macro Workbench (M-1)
// ---------------------------------------------------------------------------

export function useMacroSeries(params: {
  symbol: string
  since?: string
  until?: string
  enabled?: boolean
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['macro-series', backendId, params.symbol, params.since, params.until],
    queryFn: () => {
      const s = new URLSearchParams()
      s.set('symbol', params.symbol)
      if (params.since) s.set('since', params.since)
      if (params.until) s.set('until', params.until)
      return apiFetch<MacroSeriesResponse>(`/v1/macro/series?${s}`, { backendId })
    },
    enabled: params.enabled !== false && !!params.symbol,
    staleTime: 5 * 60_000, // 5 min — macro updates daily
  })
}

export function useMacroRatio(params: {
  numerator: string
  denominator: string
  since?: string
  until?: string
  enabled?: boolean
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: [
      'macro-ratio', backendId, params.numerator, params.denominator,
      params.since, params.until,
    ],
    queryFn: () => {
      const s = new URLSearchParams()
      s.set('numerator', params.numerator)
      s.set('denominator', params.denominator)
      if (params.since) s.set('since', params.since)
      if (params.until) s.set('until', params.until)
      return apiFetch<MacroRatioResponse>(`/v1/macro/ratio?${s}`, { backendId })
    },
    enabled: params.enabled !== false && !!params.numerator && !!params.denominator,
    staleTime: 5 * 60_000,
  })
}

export function useMacroRefresh() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (symbol?: string) => {
      const qs = symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''
      return apiFetch<MacroRefreshResponse>(`/v1/macro/refresh${qs}`, {
        method: 'POST', backendId,
      })
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['macro-series', backendId] })
      qc.invalidateQueries({ queryKey: ['macro-ratio', backendId] })
      const msg = data.failed === 0
        ? `Refreshed ${data.ok} symbols (${data.rows_touched.toLocaleString()} rows)`
        : `Refreshed ${data.ok} ok / ${data.failed} failed (${data.rows_touched.toLocaleString()} rows)`
      toast.success(msg)
    },
    onError: (err: any) =>
      toast.error(`Macro refresh failed: ${err.detail || err.message}`),
  })
}

export function useMacroSpread(params: {
  minuend: string
  subtrahend: string
  since?: string
  until?: string
  enabled?: boolean
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: [
      'macro-spread', backendId, params.minuend, params.subtrahend,
      params.since, params.until,
    ],
    queryFn: () => {
      const s = new URLSearchParams()
      s.set('minuend', params.minuend)
      s.set('subtrahend', params.subtrahend)
      if (params.since) s.set('since', params.since)
      if (params.until) s.set('until', params.until)
      return apiFetch<MacroSpreadResponse>(`/v1/macro/spread?${s}`, { backendId })
    },
    enabled: params.enabled !== false && !!params.minuend && !!params.subtrahend,
    staleTime: 5 * 60_000,
  })
}

// ---------------------------------------------------------------------------
// Boards / Watchlists (MW-2)
// ---------------------------------------------------------------------------

export function useBoards() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['boards', backendId],
    queryFn: () => apiFetch<BoardsListResponse>('/v1/boards', { backendId }),
    staleTime: 30_000,
  })
}

export function useBoard(boardId: string | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['board', backendId, boardId],
    queryFn: () => apiFetch<BoardDetail>(`/v1/boards/${boardId}`, { backendId }),
    enabled: !!boardId,
    staleTime: 30_000,
  })
}

export function useCreateBoard() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      apiFetch<BoardSummary>('/v1/boards', { method: 'POST', body: data, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['boards', backendId] })
      toast.success('Watchlist created')
    },
    onError: (err: any) => toast.error(`Create failed: ${err.detail || err.message}`),
  })
}

export function useUpdateBoard() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { id: string; name?: string; description?: string }) =>
      apiFetch<BoardSummary>(`/v1/boards/${data.id}`, {
        method: 'PATCH',
        body: { name: data.name, description: data.description },
        backendId,
      }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['boards', backendId] })
      qc.invalidateQueries({ queryKey: ['board', backendId, vars.id] })
      toast.success('Watchlist updated')
    },
    onError: (err: any) => toast.error(`Update failed: ${err.detail || err.message}`),
  })
}

export function useDeleteBoard() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/boards/${id}`, { method: 'DELETE', backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['boards', backendId] })
      toast.success('Watchlist deleted')
    },
    onError: (err: any) => toast.error(`Delete failed: ${err.detail || err.message}`),
  })
}

export function useAddTickerToBoard() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { boardId: string; ticker: string; notes?: string }) =>
      apiFetch(`/v1/boards/${data.boardId}/tickers`, {
        method: 'POST',
        body: { ticker: data.ticker, notes: data.notes },
        backendId,
      }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['boards', backendId] })
      qc.invalidateQueries({ queryKey: ['board', backendId, vars.boardId] })
    },
    onError: (err: any) => toast.error(`Add failed: ${err.detail || err.message}`),
  })
}

export function useRemoveTickerFromBoard() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { boardId: string; ticker: string }) =>
      apiFetch(`/v1/boards/${data.boardId}/tickers/${encodeURIComponent(data.ticker)}`, {
        method: 'DELETE', backendId,
      }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['boards', backendId] })
      qc.invalidateQueries({ queryKey: ['board', backendId, vars.boardId] })
    },
    onError: (err: any) => toast.error(`Remove failed: ${err.detail || err.message}`),
  })
}

export function useMoveTicker() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { sourceBoardId: string; targetBoardId: string; ticker: string }) =>
      apiFetch(`/v1/boards/${data.sourceBoardId}/tickers/move`, {
        method: 'POST',
        body: { ticker: data.ticker, target_board_id: data.targetBoardId },
        backendId,
      }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['boards', backendId] })
      qc.invalidateQueries({ queryKey: ['board', backendId, vars.sourceBoardId] })
      qc.invalidateQueries({ queryKey: ['board', backendId, vars.targetBoardId] })
      toast.success('Ticker moved')
    },
    onError: (err: any) => toast.error(`Move failed: ${err.detail || err.message}`),
  })
}

export function useQuotes(symbols: string[]) {
  const { backendId } = useBackend()
  const csv = symbols.join(',')
  return useQuery({
    queryKey: ['quotes', backendId, csv],
    queryFn: () =>
      apiFetch<QuotesResponse>(
        `/v1/quotes?symbols=${encodeURIComponent(csv)}`,
        { backendId },
      ),
    enabled: symbols.length > 0,
    staleTime: 60_000,
  })
}

// ---------------------------------------------------------------------------
// Hypotheses — M-2
// ---------------------------------------------------------------------------

export function useHypotheses(filters?: {
  status?: HypothesisStatus
  axis?: string
  claim_type?: ClaimType
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['hypotheses', backendId, filters],
    queryFn: () => {
      const s = new URLSearchParams()
      if (filters?.status) s.set('status', filters.status)
      if (filters?.axis) s.set('axis', filters.axis)
      if (filters?.claim_type) s.set('claim_type', filters.claim_type)
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<HypothesisListResponse>(`/v1/hypotheses${qs}`, { backendId })
    },
    staleTime: 60_000,
  })
}

export function useHypothesisSummary() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['hypothesis-summary', backendId],
    queryFn: () =>
      apiFetch<HypothesisSummary>(`/v1/hypotheses/summary`, { backendId }),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000, // 5min poll keeps the sidebar fresh
  })
}

export function useHypothesis(id: string | null | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['hypothesis', backendId, id],
    queryFn: () =>
      apiFetch<Hypothesis>(`/v1/hypotheses/${id}`, { backendId }),
    enabled: !!id,
    staleTime: 60_000,
  })
}

export function useCancelHypothesis() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiFetch(`/v1/hypotheses/${id}/cancel`, {
        method: 'POST',
        body: { reason },
        backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hypotheses', backendId] })
      qc.invalidateQueries({ queryKey: ['hypothesis-summary', backendId] })
    },
  })
}

// ---------------------------------------------------------------------------
// Views — M-2
// ---------------------------------------------------------------------------

export function useViews() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['views', backendId],
    queryFn: () => apiFetch<ViewsResponse>(`/v1/views`, { backendId }),
    staleTime: 5 * 60_000,
  })
}

// ---------------------------------------------------------------------------
// Research — Phase 3 / 3.7
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Admin — loop registry, fire/abort, cadences, settings (Phase 4)
// ---------------------------------------------------------------------------

export interface AdminLoopRow {
  loop_id: string
  title: string
  description: string
  default_cadence_seconds: number
  cadence_seconds: number
  supports_abort: boolean
  confirm_modal_required: boolean
  cost_sensitive: boolean
  enabled: boolean
  running: boolean
  fire_supported: boolean
  last_tick_at: string | null
  last_tick_ok: boolean | null
  last_error: string | null
  last_error_at: string | null
  last_duration_ms: number | null
  fire_cooldown_remaining_seconds: number
}

interface AdminLoopsList {
  items: AdminLoopRow[]
  count: number
}

export function useAdminLoops(opts?: { refetchMs?: number }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['admin-loops', backendId],
    queryFn: () => apiFetch<AdminLoopsList>('/v1/admin/loops', { backendId }),
    staleTime: 5_000,
    refetchInterval: opts?.refetchMs ?? 30_000,
  })
}

export function useFireLoop() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (loop_id: string) =>
      apiFetch<{ ok: boolean; loop_id: string }>(
        `/v1/admin/loops/${loop_id}/fire`,
        { method: 'POST', backendId },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-loops', backendId] })
      toast.success('Loop fired')
    },
    onError: (err: any) => {
      const detail = err?.detail
      if (detail?.error === 'rate_limited') {
        toast.error(
          `Cooldown — try again in ${Math.ceil(detail.retry_after_seconds)}s`,
        )
      } else {
        toast.error(`Fire failed: ${err?.detail || err?.message || 'unknown error'}`)
      }
    },
  })
}

export function useAbortLoop() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (loop_id: string) =>
      apiFetch<{ ok: boolean; loop_id: string }>(
        `/v1/admin/loops/${loop_id}/abort`,
        { method: 'POST', backendId },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-loops', backendId] })
      toast.success('Loop abort requested')
    },
    onError: (err: any) =>
      toast.error(`Abort failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useUpdateCadence() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      loop_id: string
      cadence_seconds: number
      enabled?: boolean
    }) =>
      apiFetch(`/v1/admin/loops/${payload.loop_id}/cadence`, {
        method: 'PUT',
        body: {
          cadence_seconds: payload.cadence_seconds,
          enabled: payload.enabled,
        },
        backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-loops', backendId] })
      toast.success('Cadence updated')
    },
    onError: (err: any) =>
      toast.error(`Update failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export interface AdminSettingsResponse {
  items: Record<string, any>
}

export function useAdminSettings() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['admin-settings', backendId],
    queryFn: () =>
      apiFetch<AdminSettingsResponse>('/v1/admin/settings', { backendId }),
    staleTime: 5_000,
    refetchInterval: 30_000,
  })
}

export function useUpdateAdminSetting() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { key: string; value: any }) =>
      apiFetch(`/v1/admin/settings/${payload.key}`, {
        method: 'PUT',
        body: { value: payload.value },
        backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-settings', backendId] })
      qc.invalidateQueries({ queryKey: ['admin-loops', backendId] })
      toast.success('Setting saved')
    },
    onError: (err: any) =>
      toast.error(`Save failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

// ---------------------------------------------------------------------------
// Costs + Retention (Phase 5)
// ---------------------------------------------------------------------------

interface CostsMonthly {
  month: string
  research_total_usd: number
  research_count: number
  vision_total_usd: number
  vision_count: number
  total_usd: number
}

interface CostsRecent {
  items: { date: string; research_usd: number; vision_usd: number }[]
  count: number
}

export function useCostsMonthly(month?: string) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['admin-costs-monthly', backendId, month ?? 'current'],
    queryFn: () => {
      const qs = month ? `?month=${month}` : ''
      return apiFetch<CostsMonthly>(`/v1/admin/costs/monthly${qs}`, { backendId })
    },
    staleTime: 5 * 60_000,
  })
}

export function useCostsRecent(days = 30) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['admin-costs-recent', backendId, days],
    queryFn: () =>
      apiFetch<CostsRecent>(`/v1/admin/costs/recent?days=${days}`, { backendId }),
    staleTime: 5 * 60_000,
  })
}

interface RetentionStatus {
  items: {
    key: string
    title: string
    ttl_days: number | string
    ttl_days_extra?: Record<string, number | string>
    row_count: number
    row_count_extra?: Record<string, number>
    oldest_at?: string | null
    purge_endpoint?: string
  }[]
  count: number
}

export function useRetentionStatus() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['admin-retention', backendId],
    queryFn: () => apiFetch<RetentionStatus>('/v1/admin/retention', { backendId }),
    staleTime: 30_000,
  })
}

export function usePurgeRetention() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { key: string; confirm: boolean }) =>
      apiFetch<{ deleted?: number; cap_reached?: boolean; preview?: boolean }>(
        `/v1/admin/retention/${payload.key}/purge`,
        {
          method: 'POST',
          body: { confirm: payload.confirm },
          backendId,
        },
      ),
    onSuccess: (data, vars) => {
      qc.invalidateQueries({ queryKey: ['admin-retention', backendId] })
      if (vars.confirm && data.deleted != null) {
        toast.success(
          data.cap_reached
            ? `Purged ${data.deleted} rows — cap reached, click again to continue`
            : `Purged ${data.deleted} rows`,
        )
      }
    },
    onError: (err: any) =>
      toast.error(`Purge failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useResearchSkills() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['research-skills', backendId],
    queryFn: () => apiFetch<ResearchSkillsList>('/v1/research/skills', { backendId }),
    staleTime: 5 * 60_000,
  })
}

export function useResearchAsk() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AskRequest) =>
      apiFetch<AskResponse>('/v1/research/ask', {
        method: 'POST',
        body: payload,
        backendId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['research-queries', backendId] })
    },
    onError: (err: any) =>
      toast.error(`Ask failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useResearchQueries(params?: {
  limit?: number
  offset?: number
  status?: string
  /** 'asked_at' (default — chronological) or 'score' (priority ranked). */
  order?: 'asked_at' | 'score'
  /** When false, hides backlog rows (is_deferred=true). Used by Today landing. */
  includeDeferred?: boolean
}) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['research-queries', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.limit) s.set('limit', String(params.limit))
      if (params?.offset) s.set('offset', String(params.offset))
      if (params?.status) s.set('status', params.status)
      if (params?.order) s.set('order', params.order)
      if (params?.includeDeferred === false) s.set('include_deferred', 'false')
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<ResearchQueriesList>(`/v1/research/queries${qs}`, { backendId })
    },
    staleTime: 30_000,
  })
}

export function useResearchQuery(id: string | null | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['research-query', backendId, id],
    queryFn: () =>
      apiFetch<ResearchQueryRead>(`/v1/research/queries/${id}`, { backendId }),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useApproveResearchQuery() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/research/queries/${id}/approve`, {
        method: 'POST',
        backendId,
      }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['research-queries', backendId] })
      qc.invalidateQueries({ queryKey: ['research-query', backendId, id] })
      qc.invalidateQueries({ queryKey: ['hypotheses', backendId] })
      toast.success('Hypothesis updated')
    },
    onError: (err: any) =>
      toast.error(`Approve failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useDismissResearchQuery() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/research/queries/${id}/dismiss`, {
        method: 'POST',
        backendId,
      }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['research-queries', backendId] })
      qc.invalidateQueries({ queryKey: ['research-query', backendId, id] })
      toast.success('Dismissed')
    },
    onError: (err: any) =>
      toast.error(`Dismiss failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

// ---------------------------------------------------------------------------
// TV Context — ingest + retrieval hooks
// ---------------------------------------------------------------------------

export function useTVContextByTicker(
  ticker: string | null | undefined,
  opts?: { includeExpired?: boolean },
) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['tv-context', backendId, ticker, opts?.includeExpired],
    queryFn: () => {
      const s = new URLSearchParams()
      if (opts?.includeExpired) s.set('include_expired', 'true')
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<TVContextItem[]>(`/v1/tv-context/by-ticker/${ticker}${qs}`, {
        backendId,
      })
    },
    enabled: !!ticker,
    staleTime: 15_000,
  })
}

export function useTVContextByTrade(tradeId: string | null | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['tv-context-trade', backendId, tradeId],
    queryFn: () =>
      apiFetch<TVContextItem[]>(`/v1/tv-context/by-trade/${tradeId}`, { backendId }),
    enabled: !!tradeId,
    staleTime: 30_000,
  })
}

export function useTVVisionSpend(month: string) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['tv-vision-spend', backendId, month],
    queryFn: () =>
      apiFetch<TVVisionSpend>(`/v1/tv-context/vision-spend?month=${month}`, {
        backendId,
      }),
    staleTime: 60_000,
  })
}

function invalidateTVContext(qc: ReturnType<typeof useQueryClient>, backendId: BackendId) {
  qc.invalidateQueries({ queryKey: ['tv-context', backendId] })
  qc.invalidateQueries({ queryKey: ['tv-vision-spend', backendId] })
}

export function useIngestTVNote() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TVNoteIngest) =>
      apiFetch<TVContextIngestResult>('/v1/tv-context/note', {
        method: 'POST',
        body,
        backendId,
      }),
    onSuccess: () => {
      invalidateTVContext(qc, backendId)
      toast.success('Note saved')
    },
    onError: (err: any) =>
      toast.error(`Note failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useIngestTVIdea() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TVIdeaIngest) =>
      apiFetch<TVContextIngestResult>('/v1/tv-context/idea', {
        method: 'POST',
        body,
        backendId,
      }),
    onSuccess: () => {
      invalidateTVContext(qc, backendId)
      toast.success('Idea saved')
    },
    onError: (err: any) =>
      toast.error(`Idea failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useIngestTVEvent() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TVEventIngest) =>
      apiFetch<TVContextIngestResult>('/v1/tv-context/event', {
        method: 'POST',
        body,
        backendId,
      }),
    onSuccess: () => {
      invalidateTVContext(qc, backendId)
      toast.success('Event saved')
    },
    onError: (err: any) =>
      toast.error(`Event failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useIngestTVScreenshot() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      file: File | Blob
      ticker: string
      note?: string
      hypothesisId?: string
      visionEnabled?: boolean
    }) => {
      const fd = new FormData()
      fd.append('file', input.file, 'chart.png')
      fd.append('ticker', input.ticker)
      if (input.note) fd.append('note', input.note)
      if (input.hypothesisId) fd.append('hypothesis_id', input.hypothesisId)
      if (input.visionEnabled !== undefined)
        fd.append('vision_enabled', String(input.visionEnabled))
      const cfg = (await import('../lib/backend-store')).getBackendConfig(backendId)
      const res = await fetch(`${cfg.baseUrl}/v1/tv-context/screenshot`, {
        method: 'POST',
        headers: { 'X-API-Key': cfg.apiKey },
        body: fd,
      })
      if (!res.ok) {
        let detail = res.statusText
        try {
          const j = await res.json()
          detail = j.detail ?? JSON.stringify(j)
        } catch {
          /* ignore */
        }
        throw new Error(detail)
      }
      return (await res.json()) as TVContextIngestResult
    },
    onSuccess: () => {
      invalidateTVContext(qc, backendId)
      toast.success('Screenshot saved')
    },
    onError: (err: any) =>
      toast.error(`Upload failed: ${err?.message || 'unknown error'}`),
  })
}

export function useArchiveTVContext() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<TVContextItem>(`/v1/tv-context/${id}/archive`, {
        method: 'POST',
        backendId,
      }),
    onSuccess: () => {
      invalidateTVContext(qc, backendId)
      toast.success('Archived')
    },
    onError: (err: any) =>
      toast.error(`Archive failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

export function useDeleteResearchQuery() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/research/queries/${id}`, {
        method: 'DELETE',
        backendId,
      }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['research-queries', backendId] })
      qc.removeQueries({ queryKey: ['research-query', backendId, id] })
      toast.success('Deleted')
    },
    onError: (err: any) =>
      toast.error(`Delete failed: ${err?.detail || err?.message || 'unknown error'}`),
  })
}

// ---------------------------------------------------------------------------
// The Street — smart-money snapshot wrapper (Phase 2 IA reorg)
// ---------------------------------------------------------------------------

export function useStreetSnapshots() {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['street-snapshots', backendId],
    queryFn: () =>
      apiFetch<StreetSnapshotsResponse>('/v1/the-street/snapshots', { backendId }),
    staleTime: 5 * 60_000,
  })
}

export function useStreetTicker(ticker: string | null | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['street-ticker', backendId, ticker?.toUpperCase()],
    queryFn: () =>
      apiFetch<StreetTickerResponse>(
        `/v1/the-street/ticker/${encodeURIComponent((ticker ?? '').toUpperCase())}`,
        { backendId },
      ),
    enabled: !!ticker,
    staleTime: 5 * 60_000,
  })
}

export function useStreetTier(
  tier: 1 | 2 | 3,
  opts?: { date?: string; includeEtfs?: boolean },
) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['street-tier', backendId, tier, opts?.date, opts?.includeEtfs],
    queryFn: () => {
      const s = new URLSearchParams()
      if (opts?.date) s.set('date', opts.date)
      if (opts?.includeEtfs) s.set('include_etfs', 'true')
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<StreetTierResponse>(`/v1/the-street/tier/${tier}${qs}`, {
        backendId,
      })
    },
    staleTime: 5 * 60_000,
  })
}

export function useStreetPolitician(name: string | null | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['street-politician', backendId, name],
    queryFn: () =>
      apiFetch<StreetPoliticianResponse>(
        `/v1/the-street/politician/${encodeURIComponent(name ?? '')}`,
        { backendId },
      ),
    enabled: !!name,
    staleTime: 5 * 60_000,
  })
}

// ---------------------------------------------------------------------------
// Vault proxy — read-only forwarder to the indexer sidecar (port 8001).
// ---------------------------------------------------------------------------

export function useVaultSearch(q: string | null | undefined, k = 8) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['vault-search', backendId, q, k],
    queryFn: () => {
      const s = new URLSearchParams({ q: q ?? '', k: String(k) })
      return apiFetch<VaultSearchResponse>(`/v1/vault/search?${s}`, { backendId })
    },
    enabled: !!q && q.length > 0,
    staleTime: 60_000,
  })
}

export function useVaultFolderContext(paths: string[]) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['vault-folder-context', backendId, paths],
    queryFn: () =>
      apiFetch<VaultFolderContextResponse>('/v1/vault/folder-context', {
        method: 'POST',
        body: { paths },
        backendId,
      }),
    enabled: paths.length > 0,
    staleTime: 5 * 60_000,
  })
}

export function useVaultNode(path: string | null | undefined) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['vault-node', backendId, path],
    queryFn: () =>
      apiFetch<VaultNodeResponse>(
        `/v1/vault/node/${encodeURI(path ?? '')}`,
        { backendId },
      ),
    enabled: !!path,
    staleTime: 60_000,
  })
}

export function useStreetDigest(
  snapshotDate: string | null | undefined,
  ticker: string | null | undefined,
  enabled: boolean = true,
) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['street-digest', backendId, snapshotDate, ticker?.toUpperCase()],
    queryFn: () =>
      apiFetch<StreetDigestResponse>(
        `/v1/the-street/digest/${encodeURIComponent(snapshotDate ?? '')}/${encodeURIComponent(
          (ticker ?? '').toUpperCase(),
        )}`,
        { backendId },
      ),
    enabled: enabled && !!snapshotDate && !!ticker,
    staleTime: 5 * 60_000,
  })
}
