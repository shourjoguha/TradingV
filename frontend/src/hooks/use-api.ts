import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, healthCheck } from '../lib/api'
import { useBackend } from './use-backend'
import type {
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
  QuotesResponse,
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

export function useOpportunities(params?: { status?: string; limit?: number }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['opportunities', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.status) s.set('status', params.status)
      if (params?.limit) s.set('limit', String(params.limit))
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<{ items: Opportunity[]; count: number }>(`/v1/opportunities${qs}`, { backendId })
    },
    refetchInterval: 60000,
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

export function useTrades(params?: { limit?: number }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['trades', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.limit) s.set('limit', String(params.limit))
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<{ items: Trade[]; count: number; pnl_summary: any }>(`/v1/trades${qs}`, { backendId })
    },
    refetchInterval: 60000,
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
