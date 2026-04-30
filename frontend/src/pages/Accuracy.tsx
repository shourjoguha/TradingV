import { useMemo, useState } from 'react'
import { useAccuracyGrid, useAccuracyPair, useEvaluateAccuracy, useDriftAlerts, useAckDriftAlert } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '../components/ui/toggle-group'
import { AlertTriangle, RefreshCw, X } from 'lucide-react'
import { InfoBubble } from '../components/common'

type DrillKey = { ticker: string; horizon: number; model: string; interval: string } | null

// n below this → cell rendered grey ("insufficient"). Avoids 0/25/50/75/100 noise.
const MIN_N = 4
// Composite-color thresholds (mape values are fractions: 0.02 = 2%).
const MAPE_GREEN = 0.02
const MAPE_RED = 0.04
const HIT_GREEN = 0.6
const HIT_OK = 0.5

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v)) return '—'
  return v.toFixed(digits)
}

// Composite color: factors directional hit-rate AND magnitude (MAPE) AND
// sample count. Fixes the "75% green but predictions were way off" case —
// directionally lucky models with high MAPE no longer read as healthy.
function compositeColor(hit_rate: number | null, mape: number, n: number): string {
  if (n < MIN_N || hit_rate == null) return 'bg-background shadow-inset-sm text-muted-foreground'
  const hit_ok = hit_rate >= HIT_GREEN
  const hit_mid = hit_rate >= HIT_OK
  if (hit_ok && mape <= MAPE_GREEN) return 'bg-success-bg text-success-fg shadow-extruded-sm hover:shadow-extruded'
  if (!hit_mid || mape > MAPE_RED) return 'bg-danger-bg text-danger-fg shadow-extruded-sm hover:shadow-extruded'
  return 'bg-warning-bg text-warning-fg shadow-extruded-sm hover:shadow-extruded'
}

export function Accuracy() {
  const [windowSize, setWindowSize] = useState(30)
  const [intervalFilter, setIntervalFilter] = useState<string>('1d')
  const [drill, setDrill] = useState<DrillKey>(null)
  const grid = useAccuracyGrid({
    last_n: windowSize,
    interval: intervalFilter === 'all' ? undefined : intervalFilter,
  })
  const drifts = useDriftAlerts()
  const evaluate = useEvaluateAccuracy()
  const ack = useAckDriftAlert()

  // Pivot rows by (ticker × horizon). Interval is filtered server-side, so
  // each (ticker, horizon) cell is unambiguous within the chosen cadence.
  const { tickers, horizons, byKey } = useMemo(() => {
    const tset = new Set<string>()
    const hset = new Set<number>()
    const map: Record<string, typeof grid.data extends { rows: Array<infer R> } ? R : any> = {}
    for (const r of grid.data?.rows ?? []) {
      tset.add(r.ticker)
      hset.add(r.horizon_offset)
      map[`${r.ticker}::${r.horizon_offset}::${r.model_id}::${r.interval}`] = r
    }
    return {
      tickers: Array.from(tset).sort(),
      horizons: Array.from(hset).sort((a, b) => a - b),
      byKey: map,
    }
  }, [grid.data])

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight flex items-center gap-2">
            Accuracy
            <InfoBubble term="composite_accuracy" />
          </h2>
          <p className="text-sm text-muted-foreground">
            Per-(ticker, horizon) Kronos performance over the rolling window. Hover a cell to see the per-prediction breakdown.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <label className="text-sm text-muted-foreground">Interval</label>
            <ToggleGroup
              type="single"
              value={intervalFilter}
              onValueChange={(v) => v && setIntervalFilter(v)}
              className="justify-start"
            >
              <ToggleGroupItem value="1d" variant="outline" size="sm" className="text-xs font-mono">1d</ToggleGroupItem>
              <ToggleGroupItem value="1h" variant="outline" size="sm" className="text-xs font-mono">1h</ToggleGroupItem>
              <ToggleGroupItem value="all" variant="outline" size="sm" className="text-xs font-mono">all</ToggleGroupItem>
            </ToggleGroup>
          </div>
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

      {/* Legend — explains composite color + low-n masking */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="font-medium">Cell:</span>
        <span className="inline-flex items-center gap-0.5">
          <span className="font-mono">hit%</span>
          <InfoBubble term="hit_rate" />
          <span> / </span>
          <span className="font-mono">MAPE%</span>
          <InfoBubble term="mape" />
          <span> · </span>
          <span className="font-mono">n=…</span>
          <InfoBubble term="sample_count" />
        </span>
        <span className="ml-2"><span className="inline-block w-3 h-3 rounded-sm bg-success-bg align-middle mr-1" />green: hit ≥ {Math.round(HIT_GREEN*100)}% AND MAPE ≤ {MAPE_GREEN*100}%</span>
        <span><span className="inline-block w-3 h-3 rounded-sm bg-warning-bg align-middle mr-1" />yellow: in-between</span>
        <span><span className="inline-block w-3 h-3 rounded-sm bg-danger-bg align-middle mr-1" />red: hit &lt; {Math.round(HIT_OK*100)}% OR MAPE &gt; {MAPE_RED*100}%</span>
        <span><span className="inline-block w-3 h-3 rounded-sm bg-background shadow-inset-sm align-middle mr-1" />grey: n &lt; {MIN_N} (insufficient)</span>
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
          <p className="text-sm">
            {intervalFilter === '1h'
              ? 'No 1h evaluations yet — schedule a 1h run to populate.'
              : 'No accuracy data yet.'}
          </p>
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
                  <th key={h} className="text-center px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">+{h}{intervalFilter === '1h' ? 'h' : 'd'}</th>
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
                    const insufficient = row.sample_count < MIN_N
                    const colorCls = compositeColor(row.hit_rate, row.mape, row.sample_count)
                    return (
                      <td key={h} className="px-1 py-1 text-center">
                        <button
                          onMouseEnter={() => setDrill({ ticker: t, horizon: h, model: row.model_id, interval: row.interval })}
                          onMouseLeave={() => setDrill(null)}
                          onFocus={() => setDrill({ ticker: t, horizon: h, model: row.model_id, interval: row.interval })}
                          onBlur={() => setDrill(null)}
                          onClick={() => setDrill({ ticker: t, horizon: h, model: row.model_id, interval: row.interval })}
                          className={`w-full px-2 py-3 rounded-xl text-xs transition-all duration-200 hover:-translate-y-[1px] ${colorCls}`}
                          aria-label={`${t} +${h} ${row.interval} hit ${fmtPct(row.hit_rate, 0)} mape ${fmtPct(row.mape)} n=${row.sample_count}`}
                        >
                          {insufficient ? (
                            <>
                              <div className="font-bold">—</div>
                              <div className="opacity-60 text-[10px]">n={row.sample_count}</div>
                            </>
                          ) : (
                            <>
                              <div className="font-bold leading-tight">
                                {fmtPct(row.hit_rate, 0)}<span className="opacity-50"> / </span>{fmtPct(row.mape, 1)}
                              </div>
                              <div className="opacity-60 text-[10px] mt-0.5">n={row.sample_count}</div>
                            </>
                          )}
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

      {drill && <DrillPanel {...drill} onClose={() => setDrill(null)} />}
    </div>
  )
}

// Inline detail panel — appears below the matrix on hover/focus instead of a
// click-to-open modal. Same content as before; faster to read at a glance.
function DrillPanel({ ticker, horizon, model, interval, onClose }: { ticker: string; horizon: number; model: string; interval: string; onClose: () => void }) {
  const pair = useAccuracyPair({ ticker, horizon_offset: horizon, model_id: model, limit: 100 })
  return (
    <div
      className="rounded-3xl bg-background shadow-extruded p-4 space-y-3"
      onMouseEnter={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between">
        <h3 className="font-display text-base font-bold">{ticker} @ +{horizon}{interval === '1h' ? 'h' : 'd'} · {model} · {interval}</h3>
        <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
      </div>
      {pair.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : (pair.data?.rows.length ?? 0) === 0 ? (
        <p className="text-sm text-muted-foreground">No evaluations yet.</p>
      ) : (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto max-h-72">
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
  )
}
