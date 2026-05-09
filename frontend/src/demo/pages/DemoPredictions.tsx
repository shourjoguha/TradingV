import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../../components/ui/table'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { Check, X, Clock } from 'lucide-react'
import { HeroStat } from '../components/HeroStat'
import { WatchWalkthrough } from '../components/WatchWalkthrough'

const PREDICTIONS_VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_PREDICTIONS as string | undefined) || null

type Tab = 'horizon' | 'target' | 'accuracy'

export function DemoPredictions() {
  const [tab, setTab] = useState<Tab>('horizon')
  const { data: accuracy } = useQuery({
    queryKey: ['demo', 'accuracy'],
    queryFn: demoApi.accuracy,
  })

  const oneDay = accuracy?.rows.find((r) => r.horizon === '1d' && !r.pending)
  const fiveDay = accuracy?.rows.find((r) => r.horizon === '5d' && !r.pending)
  const totalElapsed = accuracy?.rows.reduce((s, r) => s + (r.samples ?? 0), 0) ?? 0

  return (
    <div className="space-y-6">
      <HeroStat
        headline="Every prediction. Every miss. Receipts."
        subhead={`12 tickers, 5 horizons, ${totalElapsed} elapsed predictions in this snapshot. Each row carries entry price, predicted close, actual close, signed error, and whether the direction was right.`}
        primaryStat={
          oneDay && fiveDay ? (
            <div className="flex flex-col items-end gap-1">
              <div>
                <span className="text-violet">{(oneDay.mape! * 100).toFixed(1)}%</span>
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  MAPE @ 1d
                </span>
              </div>
              <div className="text-base font-semibold text-muted-foreground">
                {(fiveDay.mape! * 100).toFixed(1)}% MAPE @ 5d
              </div>
            </div>
          ) : (
            <span className="text-sm font-normal text-muted-foreground">loading…</span>
          )
        }
        badges={[
          { label: 'Walk-forward only', tone: 'authority' },
          { label: 'Sign-correct + magnitude tracked', tone: 'authority' },
        ]}
        walkthrough={
          <WatchWalkthrough
            youtubeId={PREDICTIONS_VIDEO_ID}
            title="Predictions — accuracy + sign correctness"
            durationSeconds={45}
          />
        }
      />

      <div className="flex gap-2">
        {(['horizon', 'target', 'accuracy'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-2xl px-4 py-1.5 text-sm transition-all ${
              tab === t
                ? 'shadow-inset-sm text-violet'
                : 'shadow-extruded-sm text-muted-foreground hover:text-foreground'
            }`}
          >
            {t === 'horizon' ? 'By Horizon' : t === 'target' ? 'By Target' : 'Accuracy'}
          </button>
        ))}
      </div>

      {tab === 'horizon' && <ByHorizon />}
      {tab === 'target' && <ByTarget />}
      {tab === 'accuracy' && <Accuracy />}
    </div>
  )
}

function fmtDelta(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return '—'
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function fmtError(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return '—'
  return `${Math.abs(pct).toFixed(2)}%`
}

function ByHorizon() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'by-horizon'],
    queryFn: demoApi.byHorizon,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />

  return (
    <div className="space-y-4">
      {data?.horizons.map((h) => {
        const elapsed = h.rows.filter((r) => r.actual !== null)
        const pending = h.rows.length - elapsed.length
        return (
          <Card key={h.horizon}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div>
                <CardTitle className="text-sm">Horizon: {h.horizon}</CardTitle>
                <CardDescription className="text-xs">
                  {h.rows.length} rows · {elapsed.length} elapsed · {pending} pending
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticker</TableHead>
                    <TableHead className="text-right">Entry</TableHead>
                    <TableHead className="text-right">Predicted</TableHead>
                    <TableHead className="text-right">Δ predicted</TableHead>
                    <TableHead className="text-right">Actual</TableHead>
                    <TableHead className="text-right">|Error|</TableHead>
                    <TableHead className="text-center">Sign</TableHead>
                    <TableHead>Target</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {h.rows.map((r) => (
                    <TableRow key={`${r.ticker}-${h.horizon}`}>
                      <TableCell className="font-mono">{r.ticker}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {r.entry_price?.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.predicted.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        <Badge variant={r.delta_pct >= 0 ? 'default' : 'secondary'}>
                          {fmtDelta(r.delta_pct)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.actual !== null ? r.actual.toFixed(2) : (
                          <span className="inline-flex items-center gap-1 text-muted-foreground">
                            <Clock className="h-3 w-3" />pending
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtError(r.error_pct)}
                      </TableCell>
                      <TableCell className="text-center">
                        {r.sign_correct === null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : r.sign_correct ? (
                          <Check className="mx-auto h-4 w-4 text-green-600" />
                        ) : (
                          <X className="mx-auto h-4 w-4 text-red-500" />
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {r.target_date}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

function ByTarget() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'by-target'],
    queryFn: demoApi.byTarget,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Per-ticker forecast matrix</CardTitle>
          <CardDescription className="text-xs">
            One row per ticker. Each cell shows predicted Δ% vs entry, with
            the actual outcome below when elapsed. Predictions made 2026-05-04.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead className="text-right">Entry</TableHead>
                  {data?.targets[0]?.horizons.map((h) => (
                    <TableHead key={h.horizon} className="text-right">
                      {h.horizon}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.targets.map((t) => (
                  <TableRow key={t.ticker}>
                    <TableCell className="font-mono">{t.ticker}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {t.entry_price.toFixed(2)}
                    </TableCell>
                    {t.horizons.map((h) => (
                      <TableCell key={h.horizon} className="text-right tabular-nums">
                        <div className="flex flex-col items-end gap-0.5">
                          <span className={`text-xs ${
                            h.delta_pct >= 0 ? 'text-green-600' : 'text-red-500'
                          }`}>
                            {fmtDelta(h.delta_pct)}
                          </span>
                          {h.actual !== null ? (
                            <span className={`flex items-center gap-1 text-[10px] ${
                              h.sign_correct ? 'text-muted-foreground' : 'text-red-500/70'
                            }`}>
                              {h.sign_correct ? (
                                <Check className="h-2.5 w-2.5" />
                              ) : (
                                <X className="h-2.5 w-2.5" />
                              )}
                              {fmtError(h.error_pct)}
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                              <Clock className="h-2.5 w-2.5" />pending
                            </span>
                          )}
                        </div>
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Reading the cells</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="text-green-600">+1.50%</span>
            <span>predicted move vs entry</span>
          </div>
          <div className="flex items-center gap-2">
            <Check className="h-3 w-3" />
            <span>direction matched the actual outcome</span>
          </div>
          <div className="flex items-center gap-2">
            <X className="h-3 w-3 text-red-500" />
            <span>direction missed; the magnitude is |predicted − actual| / actual</span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="h-3 w-3" />
            <span>horizon hasn't elapsed yet (10d targets resolve 2026-05-14)</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function Accuracy() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'accuracy'],
    queryFn: demoApi.accuracy,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Accuracy grid</CardTitle>
        <CardDescription className="text-xs">
          MAPE = mean of |predicted − actual| / actual. Hit-rate = share of
          predictions whose direction matched the actual outcome.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Horizon</TableHead>
              <TableHead className="text-right">Samples</TableHead>
              <TableHead className="text-right">MAPE</TableHead>
              <TableHead className="text-right">Hit-rate</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.rows.map((r) => (
              <TableRow key={r.horizon}>
                <TableCell>{r.horizon}</TableCell>
                <TableCell className="text-right tabular-nums">{r.samples}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.pending ? (
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      <Clock className="h-3 w-3" />pending
                    </span>
                  ) : r.mape !== null ? (
                    `${(r.mape * 100).toFixed(2)}%`
                  ) : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.pending ? '—' : r.hit_rate !== null ? `${(r.hit_rate * 100).toFixed(1)}%` : '—'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
