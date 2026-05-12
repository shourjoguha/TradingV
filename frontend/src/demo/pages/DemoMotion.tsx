import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../../components/ui/table'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { HeroStat } from '../components/HeroStat'
import { WatchWalkthrough } from '../components/WatchWalkthrough'
import { TrendingUp, TrendingDown } from 'lucide-react'

const MOTION_VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_MOTION as string | undefined) || null

type Tab = 'opportunities' | 'trades' | 'attribution'

export function DemoMotion() {
  const [tab, setTab] = useState<Tab>('opportunities')
  const { data: trades } = useQuery({
    queryKey: ['demo', 'trades'],
    queryFn: demoApi.trades,
  })

  const totalPnl = trades?.items.reduce((s, t) => s + t.pnl_pct, 0) ?? 0
  const wins = trades?.items.filter((t) => t.pnl_pct > 0).length ?? 0
  const winRate = trades?.items.length ? (wins / trades.items.length) * 100 : 0

  return (
    <div className="space-y-6">
      <HeroStat
        headline="Forecast → signal → trade → attribution. The closed loop."
        subhead="Predictions feed rules. Rules emit opportunities. The operator manually logs each closed trade with the originating opportunity_id, so per-rule P&L rolls up automatically. A rule with high hit-rate but tiny edge ranks below a rare, high-magnitude one."
        primaryStat={
          trades ? (
            <div className="flex flex-col items-end gap-1">
              <div>
                <span className={totalPnl >= 0 ? 'text-emerald-600' : 'text-red-500'}>
                  {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(1)}%
                </span>
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  ΣP&L
                </span>
              </div>
              <div className="text-base font-semibold text-muted-foreground">
                {winRate.toFixed(0)}% win-rate · {trades.items.length} trades
              </div>
            </div>
          ) : (
            <span className="text-sm font-normal text-muted-foreground">loading…</span>
          )
        }
        badges={[
          { label: 'Honest journal', tone: 'authority' },
          { label: 'Loser included', tone: 'authority' },
        ]}
        walkthrough={
          <WatchWalkthrough
            youtubeId={MOTION_VIDEO_ID}
            title="Motion — opportunities → trades → P&L"
            durationSeconds={45}
          />
        }
      />

      <BestWorstStrip />

      <div className="flex gap-2">
        {(['opportunities', 'trades', 'attribution'] as const).map((t) => (
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
            {t === 'opportunities' ? 'Opportunities'
              : t === 'trades' ? 'Trades'
              : 'Rule attribution'}
          </button>
        ))}
      </div>

      {tab === 'opportunities' && <Opportunities />}
      {tab === 'trades' && <Trades />}
      {tab === 'attribution' && <Attribution />}
    </div>
  )
}

function BestWorstStrip() {
  const { data } = useQuery({
    queryKey: ['demo', 'trades'],
    queryFn: demoApi.trades,
  })
  const { best, worst } = useMemo(() => {
    if (!data || data.items.length === 0) return { best: null, worst: null }
    const sorted = [...data.items].sort((a, b) => b.pnl_pct - a.pnl_pct)
    return { best: sorted[0], worst: sorted[sorted.length - 1] }
  }, [data])
  if (!best || !worst) return null
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            Best trade in this snapshot
          </CardTitle>
          <CardDescription className="text-xs">
            Closed for {best.pnl_pct >= 0 ? '+' : ''}{best.pnl_pct.toFixed(2)}% via the
            <span className="font-mono"> {best.rule_attribution} </span>rule.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          <span className="font-mono">{best.ticker}</span>{' '}
          <span className="capitalize">{best.side}</span> ·{' '}
          <span className="tabular-nums">{best.entry_price.toFixed(2)} → {best.exit_price.toFixed(2)}</span>{' '}
          <span className="text-muted-foreground">
            ({new Date(best.opened_at).toLocaleDateString()} → {new Date(best.closed_at).toLocaleDateString()})
          </span>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <TrendingDown className="h-4 w-4 text-red-500" />
            Biggest loser, surfaced
          </CardTitle>
          <CardDescription className="text-xs">
            {worst.pnl_pct.toFixed(2)}% on{' '}
            <span className="font-mono">{worst.rule_attribution}</span>. The honest demo
            shows the misses next to the hits.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          <span className="font-mono">{worst.ticker}</span>{' '}
          <span className="capitalize">{worst.side}</span> ·{' '}
          <span className="tabular-nums">{worst.entry_price.toFixed(2)} → {worst.exit_price.toFixed(2)}</span>{' '}
          <span className="text-muted-foreground">
            ({new Date(worst.opened_at).toLocaleDateString()} → {new Date(worst.closed_at).toLocaleDateString()})
          </span>
        </CardContent>
      </Card>
    </div>
  )
}

function Opportunities() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'opportunities'],
    queryFn: demoApi.opportunities,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />

  const counts = data?.items.reduce<Record<string, number>>((acc, o) => {
    acc[o.status] = (acc[o.status] ?? 0) + 1
    return acc
  }, {}) ?? {}

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle className="text-sm">Opportunities (frozen)</CardTitle>
          <CardDescription className="text-xs">
            {data?.items.length ?? 0} total · {counts.open ?? 0} open · {counts.acted ?? 0} acted · {counts.expired ?? 0} expired
          </CardDescription>
        </div>
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
                <TableCell>{o.rule}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {(o.score * 100).toFixed(0)}%
                </TableCell>
                <TableCell>{o.horizon}</TableCell>
                <TableCell>
                  <StatusBadge status={o.status} />
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
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

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: 'default' | 'secondary' | 'outline'; cls: string }> = {
    open: { variant: 'outline', cls: 'text-emerald-600' },
    acted: { variant: 'default', cls: '' },
    expired: { variant: 'secondary', cls: 'text-muted-foreground' },
  }
  const cfg = map[status] ?? { variant: 'outline', cls: '' }
  return <Badge variant={cfg.variant} className={cfg.cls}>{status}</Badge>
}

function Trades() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'trades'],
    queryFn: demoApi.trades,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />

  const totalPnl = data?.items.reduce((s, t) => s + t.pnl_pct, 0) ?? 0
  const wins = data?.items.filter((t) => t.pnl_pct > 0).length ?? 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle className="text-sm">Trade journal (frozen)</CardTitle>
          <CardDescription className="text-xs">
            {data?.items.length ?? 0} trades · {wins} winners · cumulative ΣP&L {totalPnl >= 0 ? '+' : ''}
            {totalPnl.toFixed(1)}%
          </CardDescription>
        </div>
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
                <TableCell>{t.rule_attribution}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
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

function Attribution() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'trades-attr'],
    queryFn: demoApi.trades,
  })
  const byRule = useMemo(() => {
    if (!data) return []
    const map = new Map<string, { rule: string; trades: number; wins: number; total_pnl: number }>()
    for (const t of data.items) {
      const k = t.rule_attribution
      const cur = map.get(k) ?? { rule: k, trades: 0, wins: 0, total_pnl: 0 }
      cur.trades += 1
      if (t.pnl_pct > 0) cur.wins += 1
      cur.total_pnl += t.pnl_pct
      map.set(k, cur)
    }
    return [...map.values()].sort((a, b) => b.total_pnl - a.total_pnl)
  }, [data])

  if (isLoading) return <Skeleton className="h-48 w-full" />

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Per-rule P&L attribution</CardTitle>
        <CardDescription className="text-xs">
          Each closed trade rolls back to the rule that produced its opportunity.
          Cumulative %P&L per rule normalises across very different trade counts so
          a rare high-magnitude rule isn't drowned out by a frequent low-edge one.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rule</TableHead>
              <TableHead className="text-right">Trades</TableHead>
              <TableHead className="text-right">Hit-rate</TableHead>
              <TableHead className="text-right">Σ P&L %</TableHead>
              <TableHead className="text-right">Avg / trade</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {byRule.map((r) => (
              <TableRow key={r.rule}>
                <TableCell>{r.rule}</TableCell>
                <TableCell className="text-right tabular-nums">{r.trades}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {((r.wins / r.trades) * 100).toFixed(0)}%
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  <Badge variant={r.total_pnl >= 0 ? 'default' : 'secondary'}>
                    {r.total_pnl >= 0 ? '+' : ''}{r.total_pnl.toFixed(2)}%
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {(r.total_pnl / r.trades).toFixed(2)}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
