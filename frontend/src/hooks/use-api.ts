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

export function useRunAnalysis() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      tickers: string[]; intervals: string[]; model_ids: string[]; horizon_bars: number
    }) => apiFetch<AnalysisJob>('/v1/analysis/run', { method: 'POST', body: data, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analysis-jobs', backendId] })
      toast.success('Analysis started')
    },
    onError: (err: any) => {
      if (err.detail === 'at_capacity') toast.error('Backend busy — retry in a few seconds')
      else toast.error(`Run failed: ${err.detail || err.message}`)
    },
  })
}
