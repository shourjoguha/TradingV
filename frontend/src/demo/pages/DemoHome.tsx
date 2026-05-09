import { useQuery } from '@tanstack/react-query'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { AlertTriangle, FileSearch, Zap, TrendingUp } from 'lucide-react'
import { AskWidget } from '../components/AskWidget'
import { HowItWorksEmbed } from '../components/HowItWorksEmbed'

const HOME_VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_TODAY as string | undefined) || null

export function DemoHome() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'today'],
    queryFn: demoApi.today,
  })

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Today</h2>
        <p className="text-sm text-zinc-400">
          Morning glance: drift, pending research, fresh signals, regime context.
        </p>
      </header>

      <HowItWorksEmbed
        youtubeId={HOME_VIDEO_ID}
        title="Today — 60 second walkthrough"
        durationSeconds={60}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              Drift alerts
            </CardTitle>
            <CardDescription>
              {isLoading ? '—' : `${data?.drift_alerts.length ?? 0} active`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : data && data.drift_alerts.length > 0 ? (
              <ul className="space-y-2">
                {data.drift_alerts.map((d) => (
                  <li key={d.id} className="flex items-center justify-between text-sm">
                    <span>
                      <span className="font-mono">{d.ticker}</span>{' '}
                      <span className="text-zinc-500">@ {d.horizon}</span>
                    </span>
                    <Badge variant="outline">×{d.ratio.toFixed(2)} vs all-time</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-500">No drift alerts in the snapshot.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <FileSearch className="h-4 w-4 text-violet" />
              Research pending
            </CardTitle>
            <CardDescription>
              {isLoading ? '—' : `${data?.research_pending.length ?? 0} queued`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : data && data.research_pending.length > 0 ? (
              <ul className="space-y-2">
                {data.research_pending.map((r) => (
                  <li key={r.id} className="text-sm text-zinc-300">
                    {r.question}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-500">Nothing queued.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Zap className="h-4 w-4 text-emerald-400" />
              Fresh signals
            </CardTitle>
            <CardDescription>
              {isLoading ? '—' : `${data?.fresh_signals.length ?? 0} new`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : data && data.fresh_signals.length > 0 ? (
              <ul className="space-y-2">
                {data.fresh_signals.map((s) => (
                  <li key={s.id} className="flex items-center justify-between text-sm">
                    <span>
                      <span className="font-mono">{s.ticker}</span>{' '}
                      <span className="text-zinc-500">·</span>{' '}
                      <span>{s.rule}</span>
                    </span>
                    <Badge variant={s.kind === 'BUY' ? 'default' : 'secondary'}>
                      {s.kind} · {(s.score * 100).toFixed(0)}%
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-500">No fresh signals in the snapshot.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <TrendingUp className="h-4 w-4 text-violet" />
              Regime
            </CardTitle>
            <CardDescription>Macro context as of cutoff</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : data?.regime ? (
              <dl className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <dt className="text-xs text-zinc-500">Label</dt>
                  <dd className="font-medium">{data.regime.label}</dd>
                </div>
                <div>
                  <dt className="text-xs text-zinc-500">VIX</dt>
                  <dd className="font-medium">
                    {data.regime.vix?.toFixed(1) ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-zinc-500">SPY 1w</dt>
                  <dd className="font-medium">
                    {data.regime.spy_pct_1w !== null && data.regime.spy_pct_1w !== undefined
                      ? `${data.regime.spy_pct_1w > 0 ? '+' : ''}${data.regime.spy_pct_1w.toFixed(1)}%`
                      : '—'}
                  </dd>
                </div>
              </dl>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <AskWidget />
    </div>
  )
}
