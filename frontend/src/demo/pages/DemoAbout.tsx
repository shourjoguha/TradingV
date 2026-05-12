import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { demoApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { ArrowRight, AlertOctagon, Wrench, Briefcase } from 'lucide-react'
import { HeroStat } from '../components/HeroStat'
import { MethodologyBadges } from '../components/MethodologyBadges'
import { WatchWalkthrough } from '../components/WatchWalkthrough'

const OVERVIEW_VIDEO_ID =
  (import.meta.env.VITE_DEMO_VIDEO_OVERVIEW as string | undefined) || null

const CONTACT =
  (import.meta.env.VITE_DEMO_CONTACT_URL as string | undefined) ??
  'mailto:guha.shourjo@gmail.com'
const GITHUB =
  (import.meta.env.VITE_DEMO_GITHUB_URL as string | undefined) ??
  'https://github.com/shourjoguha/TradingV/tree/demo'

const STACK = [
  'Python 3.12',
  'FastAPI',
  'SQLAlchemy + Alembic',
  'Postgres',
  'Kronos (candlestick model)',
  'React 18',
  'Vite + Tailwind',
  'TanStack Query',
  'Tailscale',
  'Cloudflare Pages',
  'Railway',
] as const

const FAILURE_MODES = [
  {
    name: 'Drift on a per-pair basis',
    body: 'The drift detector compares recent MAPE to all-time MAPE per (ticker, horizon) pair. When recent error exceeds 1.5× the long-run baseline, the pair gets flagged. Acked alerts age out after 90 days; unacked alerts stay forever, forcing operator review.',
  },
  {
    name: 'Earnings releases inject step-changes',
    body: 'Earnings days are step-functions the model was not conditioned on. The system maintains an earnings calendar over the roster plus smart-money tier-1/2 names and surfaces upcoming releases so the operator can throttle exposure manually around announcements.',
  },
  {
    name: 'Cohort skew by market cap',
    body: 'Per-ticker hit-rate varies materially by market cap. Mega-caps tend to forecast better day-to-day than mid-caps. The accuracy grid surfaces every (ticker, horizon) cell so the cohort skew is visible — the operator watches the per-ticker rows to know which names the model trusts itself on.',
  },
  {
    name: 'Long-horizon decay',
    body: 'Forecast error compounds with horizon — the 10d MAPE is multiples of the 1d MAPE on every ticker in the snapshot. The honest take: the further out you forecast, the more this system costs you. The accuracy grid shows the decay row by row.',
  },
] as const

export function DemoAbout() {
  const { data: manifest } = useQuery({
    queryKey: ['demo', 'manifest'],
    queryFn: demoApi.manifest,
  })

  return (
    <div className="space-y-10">
      <HeroStat
        headline="Built to be wrong out loud."
        subhead="Most trading demos hide their misses. This one surfaces them on the front page. Frozen snapshot, every prediction, every error bar — across 12 tickers."
        primaryStat={
          <div className="flex flex-col items-end">
            <span>1 operator</span>
            <span className="text-sm font-normal text-muted-foreground">
              ~6 months of solo build
            </span>
          </div>
        }
        badges={[
          { label: 'Solo-built', tone: 'authority' },
          { label: 'Open source', tone: 'authority' },
          { label: `Cutoff ${manifest?.cutoff_date ?? '2026-05-09'}`, tone: 'neutral' },
        ]}
        cta={{ label: 'Start at Today →', href: '/' }}
        walkthrough={
          <WatchWalkthrough
            youtubeId={OVERVIEW_VIDEO_ID}
            title="90-second overview"
            durationSeconds={90}
          />
        }
      />

      <section className="space-y-3">
        <h3 className="font-display text-xl font-bold">Why this exists</h3>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Trading models are easy to demo when you choose what to show. The operator built
          this because the only honest demo is one that shows the misses next to the hits.
          Predictions are stamped with an entry date. Actuals get filled in as the horizon
          elapses. Errors get tracked. The drift detector flags pairs that have started
          misbehaving. Per-rule P&L attribution lets the closed loop close. None of that is
          decorative — it's the entire point.
        </p>
      </section>

      <section className="space-y-3">
        <h3 className="flex items-center gap-2 font-display text-xl font-bold">
          <AlertOctagon className="h-5 w-5 text-amber-500" />
          Where this model breaks
        </h3>
        <p className="max-w-2xl text-sm text-muted-foreground">
          A system that names its failure modes is more trustworthy than one that pretends
          it has none. Here are the regimes where this model degrades, and how the platform
          handles each.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          {FAILURE_MODES.map((m) => (
            <Card key={m.name}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">{m.name}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{m.body}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="font-display text-xl font-bold">How it's validated</h3>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Every prediction is scored against the actual close on its target date. The grid
          you see in Predictions → Accuracy is a direct readout of those evaluations.
        </p>
        <MethodologyBadges />
      </section>

      <section className="space-y-3">
        <h3 className="flex items-center gap-2 font-display text-xl font-bold">
          <Wrench className="h-5 w-5 text-violet" />
          Stack
        </h3>
        <p className="max-w-2xl text-sm text-muted-foreground">
          One operator's laptop runs the model + DB + ingestion. Tailscale connects it to a
          Railway always-on replica that absorbs reads and webhooks. The frontend ships
          static from Cloudflare Pages. This demo is the same shape minus the model + DB.
        </p>
        <div className="flex flex-wrap gap-2">
          {STACK.map((s) => (
            <span
              key={s}
              className="rounded-full px-3 py-1 text-xs text-muted-foreground shadow-extruded-sm"
            >
              {s}
            </span>
          ))}
        </div>
      </section>

      <section className="space-y-3 rounded-2xl bg-background p-6 shadow-extruded">
        <div className="flex items-center gap-2">
          <Briefcase className="h-5 w-5 text-violet" />
          <h3 className="font-display text-xl font-bold">Working with the operator</h3>
        </div>
        <p className="max-w-2xl text-sm text-muted-foreground">
          One operator. Two engagements at a time. The patterns here — frozen demo on cheap
          infra, dual-backend laptop+cloud sync, rule engine + per-rule P&L attribution,
          vault-indexed knowledge layer — generalize past trading. Internal tools that need
          this engineering shape are a fit.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <a
            href={CONTACT}
            className="rounded-2xl bg-violet px-5 py-2 text-sm font-medium text-white shadow-extruded-sm transition-all hover:shadow-extruded"
          >
            Contact operator / start a conversation
          </a>
          <a
            href={GITHUB}
            target="_blank"
            rel="noreferrer"
            className="rounded-2xl bg-background px-5 py-2 text-sm font-medium shadow-extruded-sm transition-all hover:shadow-extruded"
          >
            Read the source on GitHub
          </a>
        </div>
      </section>

      <div className="flex flex-wrap gap-3">
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-2xl bg-background px-4 py-2 text-sm font-medium shadow-extruded-sm transition-all hover:shadow-extruded"
        >
          Try the demo <ArrowRight className="h-4 w-4" />
        </Link>
        <Link
          to="/predictions"
          className="rounded-2xl bg-background px-4 py-2 text-sm font-medium text-muted-foreground shadow-extruded-sm transition-all hover:text-foreground"
        >
          See the accuracy grid
        </Link>
        <Link
          to="/motion"
          className="rounded-2xl bg-background px-4 py-2 text-sm font-medium text-muted-foreground shadow-extruded-sm transition-all hover:text-foreground"
        >
          See P&L attribution
        </Link>
      </div>
    </div>
  )
}
