import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Sparkles, Send, ChevronDown } from 'lucide-react'
import { demoApi, type AskResponse } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import { Button } from '../../components/ui/button'
import { Textarea } from '../../components/ui/textarea'

interface CannedAnswer {
  id: string
  title: string
  tab: string
  body: string
}

/**
 * Mirror of demo-data/canned.json. Inlined here so the FAQ-when-idle
 * view always has content even before the network round-trips finish.
 * The /v1/ask endpoint remains authoritative for matched answers; this
 * is only the at-rest "browse all answers" view.
 */
const CANNED_FALLBACK: CannedAnswer[] = [
  {
    id: 'what-is-this',
    title: 'What is this app?',
    tab: 'today',
    body: "Personal trading-decision-support system. FastAPI backend runs daily Kronos candlestick forecasts on a watchlist, emits rule-based BUY/SELL opportunities, tracks per-rule P&L from manually logged trades, and layers on TV-context vision summaries, a vault-indexed research corpus, and a formal hypothesis layer with invalidator DSL. This is a frozen public demo of that system as of 2026-05-09. The live system runs locally on the operator's laptop — a Railway always-on replica was retired 2026-05-17 (ADR 018) once the laptop became the canonical runtime.",
  },
  {
    id: 'how-accurate',
    title: 'How accurate are the predictions?',
    tab: 'predictions',
    body: 'Accuracy is tracked per (horizon, target) on every prediction once actuals land. The Predictions → Accuracy tab shows MAPE and hit-rate per horizon. Drift detector flags pairs whose recent MAPE has degraded past threshold and posts to Telegram in the live system when the bot token is configured. Headline numbers in the 2026-05-09 snapshot: 1d MAPE ~1.5-2%, 5d MAPE ~4-5%, 1d hit-rate ~60%. These move every time the bake script refreshes the snapshot; check the accuracy tab for the live grid.',
  },
  {
    id: 'what-signals',
    title: 'How do opportunities get generated?',
    tab: 'motion',
    body: 'An hourly worker runs a fixed rule set over recent predictions. Current rules are threshold-based on the predicted 5d and 10d moves: a 5d ≥2% predicted gain with ≥60% historical hit-rate fires BUY; a 5d ≤−2% predicted drop fires SELL; a 10d ≥5% predicted gain with ≥55% hit-rate fires a longer-horizon BUY. Each opportunity is weighted by that rule\'s cumulative historical hit-rate so a high-volume / low-edge rule surfaces lower than a rare / high-magnitude one. Status flow: open → acted (when manually traded) or expired (after horizon). Rule set is intentionally small and hardcoded — decision support, not a discovery engine.',
  },
  {
    id: 'trade-attribution',
    title: 'How is P&L attributed to rules?',
    tab: 'motion',
    body: 'Manually logged trades carry an opportunity_id back to the rule that produced them. Per-rule P&L rolls up from every closed trade, so a rule with high hit-rate but low average win still ranks below a rare but high-magnitude rule. This closes the loop between forecast → signal → actual outcome.',
  },
  {
    id: 'model-used',
    title: 'What model produces forecasts?',
    tab: 'predictions',
    body: 'Kronos — an open candlestick prediction model. Inference runs on the operator\'s laptop (Apple-Silicon-eligible, MLX fallback). The demo ships no model weights and runs no inference; the visible forecasts are frozen historical outputs from the laptop run. A Railway always-on replica used to mirror the laptop DB over Tailscale; it was retired 2026-05-17 (ADR 018) once the laptop became the canonical runtime.',
  },
  {
    id: 'data-sources',
    title: 'What data sources feed this?',
    tab: 'today',
    body: 'Market data from yfinance for prices and IV percentile; FRED for macro signal layer (rates, spreads, employment). TradingView webhooks for text-based alert payloads, plus a separate operator-paste / drag-and-drop path for chart screenshots that get vision-summarised by Claude. A separate vault-indexer sidecar embeds an operator-curated knowledge corpus for the Research tab. None of these are called by the public demo — all data here is frozen as of the cutoff.',
  },
  {
    id: 'tech-stack',
    title: "What's the tech stack?",
    tab: 'about',
    body: 'Python 3.12 + FastAPI + SQLAlchemy + Alembic + Postgres on the backend. React 18 + Vite + TanStack Query + Tailwind on the frontend. Kronos for candlestick forecasts; Claude Sonnet 4.6 for TV-context chart vision summaries; Whisper-MLX + Qwen2-VL for YouTube ticker extraction. Vault-indexer sidecar over an Obsidian corpus for research retrieval. Cloudflare Pages hosts the static frontend; this demo backend is a thin FastAPI on Railway serving frozen JSON. The base app retired its own Railway replica 2026-05-17 — laptop is now sole runtime there.',
  },
  {
    id: 'why-frozen',
    title: 'Why is this demo frozen?',
    tab: 'about',
    body: 'Frozen-snapshot demos are cheap (no DB on the demo host), safe (no secrets, no write paths, no model), and predictable (visitors always see the same polished story). The bake script in scripts/ refreshes the JSON from the live laptop DB; the operator chooses when to re-bake.',
  },
  {
    id: 'drift-alerts',
    title: 'What is a drift alert?',
    tab: 'today',
    body: "A drift alert fires when a (ticker, horizon) pair's recent MAPE exceeds DRIFT_RATIO_THRESHOLD × the all-time MAPE for that pair. It's a coarse 'this pair is currently broken' signal, posted to Telegram in the live system when the bot token is configured and visible on the Today page here. Operator acks dismisses the row.",
  },
  {
    id: 'live-vs-demo',
    title: "What's missing vs the live app?",
    tab: 'about',
    body: 'Live app: runs Kronos inference, ingests yfinance + FRED + TradingView webhooks + operator-paste chart screenshots (Claude vision summary) + YouTube channel auto-ingest (Whisper transcripts + Qwen2-VL chart-text extraction), evaluates accuracy hourly, runs drift + research + ingestion loops, sends Telegram digests, accepts manual trade entries, evaluates formal hypotheses against an invalidator DSL, fans unknown tickers into a review queue. Demo app: serves 7 JSON files. That\'s it.',
  },
  {
    id: 'code-access',
    title: 'Can I see the source code?',
    tab: 'about',
    body: 'Yes — the demo branch is public at github.com/shourjoguha/TradingV/tree/demo. The main branch (live system) is gated; reach out via the Contact operator link in the banner.',
  },
  {
    id: 'build-with-me',
    title: 'Is something like this available as a build engagement?',
    tab: 'about',
    body: 'Open to it. The patterns here — frozen demo on cheap infra, dual-backend laptop+cloud sync, rule engine + per-rule P&L attribution, vault-indexed knowledge layer — generalize past trading. One operator, two engagements at a time. Use the Contact operator link in the banner.',
  },
]

export function AskWidget() {
  const [q, setQ] = useState('')
  const [response, setResponse] = useState<AskResponse | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Try to fetch fresh canned bundle from backend, fall back to inline.
  const { data: live } = useQuery({
    queryKey: ['demo', 'canned-list'],
    queryFn: async (): Promise<CannedAnswer[]> => {
      // The backend doesn't expose canned listing; we hit /ask with each
      // preset id title to populate. Faster: keep the inline fallback as
      // the source of truth for the at-rest list.
      return CANNED_FALLBACK
    },
    staleTime: 60 * 60 * 1000,
  })
  const answers = live ?? CANNED_FALLBACK

  const ask = useMutation({
    mutationFn: (query: string) => demoApi.ask(query),
    onSuccess: (data) => setResponse(data),
  })

  const submitPreset = (label: string) => {
    setQ(label)
    setResponse(null)
    ask.mutate(label)
  }

  const submitFreeForm = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = q.trim()
    if (trimmed) ask.mutate(trimmed)
  }

  const reset = () => {
    setQ('')
    setResponse(null)
    setExpandedId(null)
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="h-4 w-4 text-violet" />
          Ask the demo
        </CardTitle>
        <CardDescription className="text-xs">
          Twelve questions answered in full below. Click a card to expand. Or submit a custom
          query — the matcher returns the closest fit, never an empty state.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={submitFreeForm} className="space-y-2">
          <Textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. how is P&L attributed?"
            rows={2}
          />
          <div className="flex justify-between gap-2">
            {response && (
              <Button type="button" size="sm" variant="outline" onClick={reset}>
                Reset
              </Button>
            )}
            <div className="ml-auto">
              <Button type="submit" size="sm" disabled={!q.trim() || ask.isPending}>
                <Send className="mr-2 h-3 w-3" />
                {ask.isPending ? 'Asking…' : 'Ask'}
              </Button>
            </div>
          </div>
        </form>

        {response && (
          <div className="space-y-3 rounded-2xl p-4 shadow-inset-sm">
            {response.match === 'miss' ? (
              <>
                <p className="text-sm">
                  The demo doesn't cover that. Closest fits below — click to expand.
                </p>
                <div className="flex flex-wrap gap-2">
                  {response.suggestions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => submitPreset(s.label)}
                      className="rounded-2xl px-3 py-1 text-xs text-violet shadow-extruded-sm transition-all hover:shadow-extruded-hover"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">{response.answer?.title}</p>
                  <span className="rounded-full bg-violet/15 px-2 py-0.5 text-[10px] uppercase tracking-wider text-violet">
                    {response.match}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {response.answer?.body}
                </p>
              </>
            )}
          </div>
        )}

        {!response && (
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Twelve questions, in full
            </p>
            <ul className="space-y-2">
              {answers.map((a) => {
                const open = expandedId === a.id
                return (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => setExpandedId(open ? null : a.id)}
                      className="group flex w-full items-center justify-between gap-3 rounded-2xl p-3 text-left text-sm shadow-extruded-sm transition-all hover:shadow-extruded"
                    >
                      <span className="flex-1 font-medium">{a.title}</span>
                      <span className="flex items-center gap-2">
                        <span className="rounded-full bg-violet/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-violet">
                          {a.tab}
                        </span>
                        <ChevronDown
                          className={`h-4 w-4 text-muted-foreground transition-transform ${
                            open ? 'rotate-180' : ''
                          }`}
                        />
                      </span>
                    </button>
                    {open && (
                      <div className="mt-1 rounded-2xl p-4 text-sm leading-relaxed text-muted-foreground shadow-inset-sm">
                        {a.body}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
