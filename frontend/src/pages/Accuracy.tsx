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
  if (hr == null) return 'bg-muted'
  if (hr >= 0.6) return 'bg-green-500/20 text-green-300 border-green-500/40'
  if (hr >= 0.5) return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40'
  return 'bg-red-500/20 text-red-300 border-red-500/40'
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
          <h2 className="text-2xl font-semibold">Accuracy</h2>
          <p className="text-sm text-muted-foreground">
            Per-(ticker, horizon) Kronos performance over the rolling window. Click a cell to drill down.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-muted-foreground">Window</label>
          <select
            value={windowSize}
            onChange={(e) => setWindowSize(parseInt(e.target.value, 10))}
            className="bg-background border rounded px-2 py-1 text-sm"
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
            <div key={d.id} className="flex items-center gap-3 p-3 border border-yellow-500/40 bg-yellow-500/10 rounded">
              <AlertTriangle className="h-4 w-4 text-yellow-500 shrink-0" />
              <div className="flex-1 text-sm">
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
        <div className="border rounded p-8 text-center text-muted-foreground">
          <p className="text-sm">No accuracy data yet.</p>
          <p className="text-xs mt-2">
            Predictions need to elapse and have actuals fetched before they're evaluated.
            Hit "Evaluate" or wait for the hourly background tick.
          </p>
        </div>
      ) : (
        <div className="border rounded overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Ticker</th>
                {horizons.map((h) => (
                  <th key={h} className="text-center px-3 py-2 font-medium">+{h}d</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tickers.map((t) => (
                <tr key={t} className="border-t">
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
                          className={`w-full px-2 py-2 rounded border text-xs hover:scale-105 transition-transform ${hitRateColor(row.hit_rate)}`}
                          title={`MAPE ${fmtPct(row.mape)} · RMSE ${fmtNum(row.rmse)} · n=${row.sample_count}`}
                        >
                          <div className="font-semibold">{fmtPct(row.hit_rate, 0)}</div>
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
      <div className="bg-card border rounded-lg w-full max-w-4xl my-8 p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{ticker} @ +{horizon}d · {model}</h3>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        {pair.isLoading ? (
          <Skeleton className="h-60 w-full" />
        ) : (pair.data?.rows.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">No evaluations yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/40">
                <tr>
                  <th className="text-left px-2 py-1">Made on</th>
                  <th className="text-left px-2 py-1">Target</th>
                  <th className="text-right px-2 py-1">Predicted</th>
                  <th className="text-right px-2 py-1">Actual</th>
                  <th className="text-right px-2 py-1">Baseline</th>
                  <th className="text-right px-2 py-1">Err %</th>
                  <th className="text-center px-2 py-1">Dir</th>
                </tr>
              </thead>
              <tbody>
                {pair.data!.rows.map((r) => (
                  <tr key={r.prediction_id} className="border-t">
                    <td className="px-2 py-1 font-mono">{r.made_on}</td>
                    <td className="px-2 py-1 font-mono">{r.target_date}</td>
                    <td className="px-2 py-1 text-right font-mono">{fmtNum(r.predicted_close)}</td>
                    <td className="px-2 py-1 text-right font-mono">{fmtNum(r.actual_close)}</td>
                    <td className="px-2 py-1 text-right font-mono">{fmtNum(r.baseline_close)}</td>
                    <td className={`px-2 py-1 text-right font-mono ${r.error_pct > 0 ? 'text-green-400' : r.error_pct < 0 ? 'text-red-400' : ''}`}>
                      {fmtPct(r.error_pct)}
                    </td>
                    <td className="px-2 py-1 text-center">
                      {r.direction_correct === true ? '✓' : r.direction_correct === false ? '✗' : '—'}
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
