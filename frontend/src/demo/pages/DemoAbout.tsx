import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Button } from '../../components/ui/button'
import { ArrowRight, Lock, Database, Cpu } from 'lucide-react'
import { HowItWorksEmbed } from '../components/HowItWorksEmbed'

const OVERVIEW_VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_OVERVIEW as string | undefined) || null

export function DemoAbout() {
  const { data: manifest } = useQuery({
    queryKey: ['demo', 'manifest'],
    queryFn: demoApi.manifest,
  })

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h2 className="text-3xl font-semibold tracking-tight">
          Personal trading-decision-support, end to end.
        </h2>
        <p className="max-w-2xl text-zinc-400">
          FastAPI backend running daily Kronos forecasts on a watchlist. Rule
          engine emits BUY/SELL opportunities weighted by historical hit-rate.
          Manual trades close the loop with per-rule P&L attribution. This is
          a frozen public demo of that system as of {manifest?.cutoff_date ?? '2026-05-09'}.
        </p>
      </div>

      <HowItWorksEmbed
        youtubeId={OVERVIEW_VIDEO_ID}
        title="90-second overview"
        durationSeconds={90}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex-row items-center gap-2 pb-2">
            <Database className="h-4 w-4 text-violet" />
            <CardTitle className="text-sm">What's real here</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-400">
            Frozen JSON snapshot of real predictions, opportunities, and trades —
            scrubbed of PII and proprietary feeds.
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center gap-2 pb-2">
            <Lock className="h-4 w-4 text-violet" />
            <CardTitle className="text-sm">What's locked down</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-400">
            No DB. No model weights. No write paths. No outbound API calls.
            CORS allow-list, healthcheck, rate limits in front.
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center gap-2 pb-2">
            <Cpu className="h-4 w-4 text-violet" />
            <CardTitle className="text-sm">What runs upstream</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-400">
            Live system runs on the operator's laptop with a Tailscale-synced
            Railway replica, vault-indexer sidecar, and Telegram alerts.
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link to="/">
            Try it <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/predictions">See accuracy</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/motion">See P&L attribution</Link>
        </Button>
      </div>
    </div>
  )
}
