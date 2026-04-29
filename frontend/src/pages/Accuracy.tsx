import { useMemo, useState } from 'react'
import { useAccuracyGrid, useAccuracyPair, useEvaluateAccuracy, useDriftAlerts, useAckDriftAlert } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { AlertTriangle, RefreshCw, X } from 'lucide-react'

type DrillKey = { ticker: string; horizon: number; model: string } | null

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v)) return '—'
  return v.toFixed(digits)
}

function hitRateColor(hr: number | null): string {
  if (hr == null) return 'bg-background shadow-inset-sm text-muted-foreground'
  if (hr >= 0.6) return 'bg-success-bg text-success-fg shadow-extruded-sm hover:shadow-extruded'
  if (hr >= 0.5) return 'bg-warning-bg text-warning-fg shadow-extruded-sm hover:shadow-extruded'
  return 'bg-danger-bg text-danger-fg shadow-extruded-sm hover:shadow-extruded'
}

export function Accuracy() {
  const [windowSize, setWindowSize] = useState(30)
  const [drill, setDrill] = useState<DrillKey>(null)
  const grid = useAccuracyGrid({ last_n: windowSize })
  const drifts = useDriftAlerts()
  const evaluate = useEvaluateAccuracy()
  const ack = useAckDriftAlert()

  // Pivot rows by (ticker × horizon).
  const { tickers, horizons, byKey } = useMemo(() => {
    const tset = new Set<string>()
    const hset = new Set<number>()
    const map: Record<string, typeof grid.data extends { rows: Array<infer R> } ? R : any> = {}
    for (const r of grid.data?.rows ?? []) {
      tset.add(r.ticker)
      hset.add(r.horizon_offset)
      map[`${r.ticker}::${r.horizon_offset}::${r.model_id}`] = r
    }
    return {
      tickers: Array.from(tset).sort(),
      horizons: Array.from(hset).sort((a, b) => a - b),
      byKey: map,
    }
  }, [grid.data])

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight">Accuracy</h2>
          <p className="text-sm text-muted-foreground">
            Per-(ticker, horizon) Kronos performance over the rolling window. Click a cell to drill down.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-muted-foreground">Window</label>
          <select
            value={windowSize}
            onChange={(e) => setWindowSize(parseInt(e.target.value, 10))}
            className="bg-background rounded-xl px-3 py-2 text-sm shadow-inset-sm focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-violet"
          >
            <option value={10}>last 10</option>
            <option value={30}>last 30</option>
            <option value={100}>last 100</option>
            <option value={500}>last 500</option>
          </select>
          <Button variant="outline" size="sm" onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
            <RefreshCw className={`h-4 w-4 mr-2 ${evaluate.isPending ? 'animate-spin' : ''}`} />
            Evaluate
          </Button>
        </div>
      </div>

      {(drifts.data?.alerts.length ?? 0) > 0 && (
        <div className="space-y-2">
          {drifts.data!.alerts.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-4 rounded-2xl bg-warning-bg shadow-extruded-sm">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
              <div className="flex-1 text-sm text-warning-fg">
                <span className="font-medium">{d.ticker}@{d.horizon_offset}d ({d.model_id})</span>
                {' '}drift detected — recent MAPE {fmtPct(d.recent_mape)} vs all-time {fmtPct(d.all_time_mape)}
                {' '}({d.ratio.toFixed(2)}× degradation).
              </div>
              <Button variant="ghost" size="sm" onClick={() => ack.mutate(d.id)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {grid.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : tickers.length === 0 ? (
        <div className="rounded-3xl shadow-inset-sm p-8 text-center text-muted-foreground bg-background">
          <p className="text-sm">No accuracy data yet.</p>
          <p className="text-xs mt-2">
            Each prediction needs its target date to elapse <em>and</em> the matching actual close to land in the OHLCV cache before a pair is formed.
            Pairs are computed automatically: hourly via the evaluator loop, plus immediately after each scheduled daily run.
            Hit <span className="font-medium">Evaluate</span> above to force a pass now.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Ticker</th>
                {horizons.map((h) => (
                  <th key={h} className="text-center px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">+{h}d</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tickers.map((t) => (
                <tr key={t}>
                  <td className="px-3 py-2 font-mono text-xs">{t}</td>
                  {horizons.map((h) => {
                    const row = Object.values(byKey).find(
                      (r: any) => r.ticker === t && r.horizon_offset === h,
                    ) as any
                    if (!row) {
                      return <td key={h} className="px-2 py-1 text-center text-muted-foreground/40">—</td>
                    }
                    return (
                      <td key={h} className="px-1 py-1 text-center">
                        <button
                          onClick={() => setDrill({ ticker: t, horizon: h, model: row.model_id })}
                          className={`w-full px-2 py-3 rounded-xl text-xs transition-all duration-200 hover:-translate-y-[1px] ${hitRateColor(row.hit_rate)}`}
                          title={`MAPE ${fmtPct(row.mape)} · RMSE ${fmtNum(row.rmse)} · n=${row.sample_count}`}
                        >
                          <div className="font-bold">{fmtPct(row.hit_rate, 0)}</div>
                          <div className="opacity-60 text-[10px]">n={row.sample_count}</div>
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {drill && <DrillModal {...drill} onClose={() => setDrill(null)} />}
    </div>
  )
}

function DrillModal({ ticker, horizon, model, onClose }: { ticker: string; horizon: number; model: string; onClose: () => void }) {
  const pair = useAccuracyPair({ ticker, horizon_offset: horizon, model_id: model, limit: 100 })
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-start justify-center p-6 overflow-y-auto" onClick={onClose}>
      <div className="bg-background rounded-3xl shadow-extruded w-full max-w-4xl my-8 p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg font-bold">{ticker} @ +{horizon}d · {model}</h3>
          <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        {pair.isLoading ? (
          <Skeleton className="h-60 w-full" />
        ) : (pair.data?.rows.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">No evaluations yet.</p>
        ) : (
          <div className="rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  <th className="text-left px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Made on</th>
                  <th className="text-left px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Target</th>
                  <th className="text-right px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Predicted</th>
                  <th className="text-right px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Actual</th>
                  <th className="text-right px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Baseline</th>
                  <th className="text-right px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Err %</th>
                  <th className="text-center px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Dir</th>
                </tr>
              </thead>
              <tbody>
                {pair.data!.rows.map((r) => (
                  <tr key={r.prediction_id} className="hover:bg-white/30">
                    <td className="px-2 py-1.5 font-mono">{r.made_on}</td>
                    <td className="px-2 py-1.5 font-mono">{r.target_date}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fmtNum(r.predicted_close)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fmtNum(r.actual_close)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fmtNum(r.baseline_close)}</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${r.error_pct > 0 ? 'text-success' : r.error_pct < 0 ? 'text-danger' : ''}`}>
                      {fmtPct(r.error_pct)}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      {r.direction_correct === true ? <span className="text-success">✓</span> : r.direction_correct === false ? <span className="text-danger">✗</span> : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
