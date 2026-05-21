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
  'Postgres (local)',
  'Kronos (candlestick model)',
  'Claude Sonnet 4.6 (TV-context vision)',
  'Whisper-MLX + Qwen2-VL (video ingest)',
  'Vault-indexer (Obsidian corpus)',
  'React 18',
  'Vite + Tailwind',
  'TanStack Query',
  'Cloudflare Pages (demo frontend)',
  'Railway (demo backend host)',
] as const

const PILLARS = [
  {
    name: 'Predictions',
    body: 'Daily Kronos candlestick forecasts across the watchlist, scored against actual closes once each horizon elapses. Surfaced in this demo.',
    state: 'shipped',
  },
  {
    name: 'Opportunities + per-rule attribution',
    body: 'Hourly rule engine emits BUY/SELL signals weighted by historical hit-rate. Manually logged trades carry the originating opportunity_id so per-rule P&L rolls up automatically. Surfaced in this demo.',
    state: 'shipped',
  },
  {
    name: 'Drift detection',
    body: 'Per-(ticker, horizon) MAPE-ratio detector with operator-ack. Telegram-notified in the live system when configured. Surfaced in this demo.',
    state: 'shipped',
  },
  {
    name: 'Vault-indexed research',
    body: 'Operator-curated Obsidian knowledge corpus, embedded by a local indexer sidecar. The Research tab in the live system retrieves over it and answers stress-test questions; the weekly stress-test loop is opt-in. Operator surface — not in this demo.',
    state: 'operator-only',
  },
  {
    name: 'TV-context (chart-screenshot vision)',
    body: 'Operator pastes a TradingView screenshot; Claude Sonnet 4.6 returns a structured chart summary. The system stamps an attention score, feeds the hypothesis layer, and queues unknown tickers for review. Operator surface — not in this demo.',
    state: 'operator-only',
  },
  {
    name: 'Hypothesis layer + invalidator DSL',
    body: 'Each research question can graduate into a tracked hypothesis with an explicit invalidator expression (e.g. tv_context_stance_count_since). The daily evaluator marks hypotheses ACTIVE / INVALIDATED / NEEDS_CONTEXT. Operator surface — not in this demo.',
    state: 'operator-only',
  },
  {
    name: 'Earnings calendar gating',
    body: 'Earnings days are step-functions Kronos was not conditioned on. The system maintains an earnings calendar over the watchlist + smart-money tier-1/2 names and surfaces upcoming releases so exposure can be throttled manually. Operator surface — not in this demo.',
    state: 'operator-only',
  },
  {
    name: 'Video-vision ingest (YouTube)',
    body: 'Opt-in channels get auto-ingested: Whisper-MLX transcribes the audio, Qwen2-VL extracts on-chart tickers, the result lands in the vault and unknown tickers fan into the review queue. Apple-Silicon-only. Operator surface — not in this demo.',
    state: 'operator-only',
  },
  {
    name: 'Ticker review queue',
    body: 'A single inbox for unknown-symbol mentions surfaced by video-vision or TV-context. Operator approves / rejects / labels. Keeps the watchlist honest. Operator surface — not in this demo.',
    state: 'operator-only',
  },
  {
    name: 'Macro / sectors workbench',
    body: 'Regime-aware research surface — cycle wheel, rotation-bump chart, correlation heatmap with rolling-pair drill-in, configurable cadences. Operator surface — not in this demo.',
    state: 'operator-only',
  },
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
    body: 'Forecast error compounds with horizon — the 10d MAPE is multiples of the 1d MAPE on every ticker in the snapshot. The honest take: the further out the model forecasts, the more error it carries. The accuracy grid shows the decay row by row.',
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
          Trading models are easy to demo when the author chooses what to show. The operator
          built this because the only honest demo is one that shows the misses next to the hits.
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
          rendered in Predictions → Accuracy is a direct readout of those evaluations.
        </p>
        <MethodologyBadges />
      </section>

      <section className="space-y-3">
        <h3 className="flex items-center gap-2 font-display text-xl font-bold">
          <Wrench className="h-5 w-5 text-violet" />
          Stack
        </h3>
        <p className="max-w-2xl text-sm text-muted-foreground">
          One operator's laptop runs the model + DB + ingestion + vault + indexer.
          The base app's Railway always-on replica was retired 2026-05-17 (ADR 018) once
          the laptop became the canonical runtime. This demo is a separate concern: a
          frozen JSON snapshot served from a tiny FastAPI on Railway, with the frontend
          on Cloudflare Pages. Cheap, idle, no secrets, no model, no DB.
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

      <section className="space-y-3">
        <h3 className="font-display text-xl font-bold">System map</h3>
        <p className="max-w-2xl text-sm text-muted-foreground">
          The closed loop has more pillars than the four tabs in this demo can show.
          Each row below is a layer of the live system. Three of them are surfaced
          here directly — the rest are operator surfaces that aren't safe to expose
          publicly (paste-screenshot ingest, vault corpus, hypothesis evaluator, etc).
          The honest demo names them rather than hiding them.
        </p>
        <ul className="space-y-2">
          {PILLARS.map((p) => (
            <li
              key={p.name}
              className="flex items-start gap-3 rounded-2xl bg-background p-3 shadow-extruded-sm"
            >
              <span
                className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                  p.state === 'shipped'
                    ? 'bg-emerald-500/15 text-emerald-700'
                    : 'bg-violet/15 text-violet'
                }`}
              >
                {p.state === 'shipped' ? 'in demo' : 'operator-only'}
              </span>
              <div className="space-y-0.5">
                <p className="text-sm font-medium">{p.name}</p>
                <p className="text-xs leading-relaxed text-muted-foreground">{p.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3 rounded-2xl bg-background p-6 shadow-extruded">
        <div className="flex items-center gap-2">
          <Briefcase className="h-5 w-5 text-violet" />
          <h3 className="font-display text-xl font-bold">Working with the operator</h3>
        </div>
        <p className="max-w-2xl text-sm text-muted-foreground">
          One operator. Two engagements at a time. The patterns here — frozen demo on cheap
          infra, rule engine + per-rule P&L attribution, vault-indexed knowledge layer,
          chart-screenshot vision summarisation, formal hypothesis evaluator with
          invalidator DSL, video-vision ingest for content-driven signal — generalize past
          trading. Internal tools that need this engineering shape are a fit.
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
