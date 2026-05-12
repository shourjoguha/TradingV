import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { AlertTriangle, FileSearch, Zap, TrendingUp, Plus, Minus } from 'lucide-react'
import { AskWidget } from '../components/AskWidget'
import { HeroStat } from '../components/HeroStat'
import { WatchWalkthrough } from '../components/WatchWalkthrough'

const TODAY_VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_TODAY as string | undefined) || null

export function DemoHome() {
  const { data, isLoading } = useQuery({
    queryKey: ['demo', 'today'],
    queryFn: demoApi.today,
  })
  const { data: accuracy } = useQuery({
    queryKey: ['demo', 'accuracy'],
    queryFn: demoApi.accuracy,
  })

  // Hero stat: pick the strongest 1d row and contrast with longest elapsed horizon
  const oneDay = accuracy?.rows.find((r) => r.horizon === '1d' && !r.pending)
  const fiveDay = accuracy?.rows.find((r) => r.horizon === '5d' && !r.pending)

  return (
    <div className="space-y-6">
      <HeroStat
        headline="A trading model that admits when it's wrong."
        subhead="Every prediction is on display across 12 tickers and 5 horizons — alongside exactly how each one missed. No cherry-picked screenshots, no PR-massaged numbers."
        primaryStat={
          oneDay && fiveDay ? (
            <div className="flex flex-col items-end gap-1">
              <div>
                <span className="text-violet">{(oneDay.hit_rate! * 100).toFixed(0)}%</span>
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  sign-correct @ 1d
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
          { label: 'Walk-forward validation', tone: 'authority' },
          { label: 'No look-ahead leakage', tone: 'authority' },
          { label: '12 tickers · 5 horizons · frozen 2026-05-09', tone: 'neutral' },
        ]}
        cta={{ label: 'See where this model breaks →', href: '/about' }}
        walkthrough={
          <WatchWalkthrough
            youtubeId={TODAY_VIDEO_ID}
            title="Today — 60 second walkthrough"
            durationSeconds={60}
          />
        }
      />

      <div>
        <h3 className="font-display text-lg font-semibold">Today, frozen</h3>
        <p className="text-sm text-muted-foreground">
          What the operator's morning glance looks like. Four signals at once: where the model
          is misfiring, what the rules might pursue, what the system is curious about, and the
          macro mood.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                Where the model is misfiring
              </CardTitle>
              <CardDescription className="text-xs">
                Drift = recent MAPE ratio vs all-time. The system flags itself before the operator does.
              </CardDescription>
            </div>
            <span className="text-xs text-muted-foreground">
              {isLoading ? '—' : `${data?.drift_alerts.length ?? 0} active`}
            </span>
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
                      <span className="text-muted-foreground">@ {d.horizon}</span>
                    </span>
                    <Badge variant="outline">×{d.ratio.toFixed(2)} vs all-time</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No drift alerts in this snapshot. The model is performing within its
                historical envelope across all (ticker, horizon) pairs.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <Zap className="h-4 w-4 text-emerald-500" />
                What it might pursue
              </CardTitle>
              <CardDescription className="text-xs">
                Rule-based signals weighted by historical hit-rate. Decision support, not auto-execution.
              </CardDescription>
            </div>
            <span className="text-xs text-muted-foreground">
              {isLoading ? '—' : `${data?.fresh_signals.length ?? 0} fresh`}
            </span>
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
                      <span className="text-muted-foreground">·</span>{' '}
                      <span>{s.rule}</span>
                    </span>
                    <Badge variant={s.kind === 'BUY' ? 'default' : 'secondary'}>
                      {s.kind} · {(s.score * 100).toFixed(0)}%
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No fresh signals in this snapshot.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <FileSearch className="h-4 w-4 text-violet" />
                What it's curious about
              </CardTitle>
              <CardDescription className="text-xs">
                Stress-test questions the operator has queued against the curated knowledge vault. The automatic weekly stress-test loop is gated off by default to keep API spend bounded; the operator opts in.
              </CardDescription>
            </div>
            <span className="text-xs text-muted-foreground">
              {isLoading ? '—' : `${data?.research_pending.length ?? 0} pending`}
            </span>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : data && data.research_pending.length > 0 ? (
              <ul className="space-y-2 text-sm">
                {data.research_pending.map((r) => (
                  <li key={r.id} className="leading-snug">
                    {r.question}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nothing queued.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <TrendingUp className="h-4 w-4 text-violet" />
              Market mood right now
            </CardTitle>
            <CardDescription className="text-xs">
              Macro context: regime label, VIX, SPY 1-week move, watchlist deltas.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : data?.regime ? (
              <>
                <dl className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Label</dt>
                    <dd className="font-medium capitalize">
                      {data.regime.label.replace('-', ' ')}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">VIX</dt>
                    <dd className="font-medium tabular-nums">
                      {data.regime.vix?.toFixed(1) ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">SPY 1w</dt>
                    <dd className="font-medium tabular-nums">
                      {data.regime.spy_pct_1w !== null && data.regime.spy_pct_1w !== undefined
                        ? `${data.regime.spy_pct_1w > 0 ? '+' : ''}${data.regime.spy_pct_1w.toFixed(1)}%`
                        : '—'}
                    </dd>
                  </div>
                </dl>
                {data.watchlist_delta && data.watchlist_delta.length > 0 && (
                  <div className="border-t border-foreground/5 pt-3">
                    <p className="mb-2 text-xs text-muted-foreground">Watchlist deltas</p>
                    <ul className="space-y-1 text-xs">
                      {(data.watchlist_delta as Array<{ ticker: string; added: boolean; reason: string }>).map((w) => (
                        <li key={w.ticker} className="flex items-start gap-2">
                          {w.added ? (
                            <Plus className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                          ) : (
                            <Minus className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                          )}
                          <span>
                            <span className="font-mono">{w.ticker}</span>{' '}
                            <span className="text-muted-foreground">{w.reason}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="rounded-2xl bg-background p-6 shadow-extruded-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-display text-base font-semibold">
              Want to see the closed loop?
            </p>
            <p className="text-sm text-muted-foreground">
              Predictions feed rules. Rules feed opportunities. Opportunities feed trades
              (manually logged with the rule attribution). Trades feed back into per-rule P&L.
              The whole pipeline is on Motion.
            </p>
          </div>
          <Link
            to="/motion"
            className="self-start rounded-2xl bg-violet px-4 py-2 text-sm font-medium text-white shadow-extruded-sm transition-all hover:shadow-extruded md:self-auto"
          >
            See P&L attribution →
          </Link>
        </div>
      </div>

      <AskWidget />
    </div>
  )
}
