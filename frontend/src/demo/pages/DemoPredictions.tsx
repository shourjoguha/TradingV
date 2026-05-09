import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../../components/ui/table'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { HowItWorksEmbed } from '../components/HowItWorksEmbed'

type Tab = 'horizon' | 'target' | 'accuracy'

const VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_PREDICTIONS as string | undefined) || null

export function DemoPredictions() {
  const [tab, setTab] = useState<Tab>('horizon')

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Predictions</h2>
        <p className="text-sm text-zinc-400">
          Frozen forecasts from the laptop run, accuracy grid, sign-correctness.
        </p>
      </header>

      <HowItWorksEmbed
        youtubeId={VIDEO_ID}
        title="Predictions — how Kronos drives forecasts"
        durationSeconds={45}
      />

      <div className="flex gap-2">
        {(['horizon', 'target', 'accuracy'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm transition ${
              tab === t
                ? 'bg-violet/15 text-violet'
                : 'bg-zinc-900 text-zinc-400 hover:text-zinc-100'
            }`}
          >
            By {t === 'horizon' ? 'Horizon' : t === 'target' ? 'Target' : 'Accuracy'}
          </button>
        ))}
      </div>

      {tab === 'horizon' && <ByHorizon />}
      {tab === 'target' && <ByTarget />}
      {tab === 'accuracy' && <Accuracy />}
    </div>
  )
}

function ByHorizon() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'by-horizon'],
    queryFn: demoApi.byHorizon,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />
  return (
    <div className="space-y-4">
      {data?.horizons.map((h) => (
        <Card key={h.horizon}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Horizon: {h.horizon}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead className="text-right">Predicted</TableHead>
                  <TableHead className="text-right">Current</TableHead>
                  <TableHead className="text-right">Δ %</TableHead>
                  <TableHead>As of</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {h.rows.map((r, i) => (
                  <TableRow key={`${r.ticker}-${i}`}>
                    <TableCell className="font-mono">{r.ticker}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.predicted?.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.current?.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Badge variant={r.delta_pct >= 0 ? 'default' : 'secondary'}>
                        {r.delta_pct >= 0 ? '+' : ''}
                        {r.delta_pct?.toFixed(2)}%
                      </Badge>
                    </TableCell>
                    <TableCell className="text-zinc-500">{r.as_of}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function ByTarget() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'by-target'],
    queryFn: demoApi.byHorizon, // reuse — placeholder; adjust if endpoint differs
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Forecasts pivoted by target</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-zinc-400">
          Same data, transposed by ticker so you can scan a single name across
          horizons. {data ? `${data.horizons.reduce((acc, h) => acc + h.rows.length, 0)} rows in snapshot.` : ''}
        </p>
      </CardContent>
    </Card>
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
                  {(r.mape * 100).toFixed(2)}%
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {(r.hit_rate * 100).toFixed(1)}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
