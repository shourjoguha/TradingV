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

type Tab = 'opportunities' | 'trades'

const VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_MOTION as string | undefined) || null

export function DemoMotion() {
  const [tab, setTab] = useState<Tab>('opportunities')

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Motion</h2>
        <p className="text-sm text-zinc-400">
          Rule-based opportunities and the trades they ultimately fed.
        </p>
      </header>

      <HowItWorksEmbed
        youtubeId={VIDEO_ID}
        title="Motion — opportunities → trades → P&L"
        durationSeconds={45}
      />

      <div className="flex gap-2">
        {(['opportunities', 'trades'] as const).map((t) => (
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
            {t === 'opportunities' ? 'Opportunities' : 'Trades'}
          </button>
        ))}
      </div>

      {tab === 'opportunities' ? <Opportunities /> : <Trades />}
    </div>
  )
}

function Opportunities() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'opportunities'],
    queryFn: demoApi.opportunities,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Opportunities (frozen)</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticker</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Rule</TableHead>
              <TableHead className="text-right">Score</TableHead>
              <TableHead>Horizon</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((o) => (
              <TableRow key={o.id}>
                <TableCell className="font-mono">{o.ticker}</TableCell>
                <TableCell>
                  <Badge variant={o.kind === 'BUY' ? 'default' : 'secondary'}>
                    {o.kind}
                  </Badge>
                </TableCell>
                <TableCell className="text-zinc-300">{o.rule}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {(o.score * 100).toFixed(0)}%
                </TableCell>
                <TableCell>{o.horizon}</TableCell>
                <TableCell>
                  <Badge variant="outline" className={o.status === 'open' ? 'border-emerald-500 text-emerald-400' : 'text-zinc-500'}>
                    {o.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-zinc-500">
                  {new Date(o.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function Trades() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'trades'],
    queryFn: demoApi.trades,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Trade journal (frozen)</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticker</TableHead>
              <TableHead>Side</TableHead>
              <TableHead className="text-right">Entry</TableHead>
              <TableHead className="text-right">Exit</TableHead>
              <TableHead className="text-right">P&L %</TableHead>
              <TableHead>Rule</TableHead>
              <TableHead>Closed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((t) => (
              <TableRow key={t.id}>
                <TableCell className="font-mono">{t.ticker}</TableCell>
                <TableCell className="capitalize">{t.side}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {t.entry_price?.toFixed(2)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {t.exit_price?.toFixed(2)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  <Badge variant={t.pnl_pct >= 0 ? 'default' : 'secondary'}>
                    {t.pnl_pct >= 0 ? '+' : ''}
                    {t.pnl_pct?.toFixed(2)}%
                  </Badge>
                </TableCell>
                <TableCell className="text-zinc-300">{t.rule_attribution}</TableCell>
                <TableCell className="text-zinc-500">
                  {new Date(t.closed_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
