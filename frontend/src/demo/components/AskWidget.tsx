import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Sparkles, Send } from 'lucide-react'
import { demoApi, type AskResponse } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Button } from '../../components/ui/button'
import { Textarea } from '../../components/ui/textarea'

const PRESETS = [
  { id: 'what-is-this', label: 'What is this app?' },
  { id: 'how-accurate', label: 'How accurate are the predictions?' },
  { id: 'what-signals', label: 'How do opportunities get generated?' },
  { id: 'trade-attribution', label: 'How is P&L attributed to rules?' },
  { id: 'model-used', label: 'What model produces forecasts?' },
  { id: 'data-sources', label: 'What data sources feed this?' },
  { id: 'tech-stack', label: "What's the tech stack?" },
  { id: 'why-frozen', label: 'Why is this demo frozen?' },
  { id: 'drift-alerts', label: 'What is a drift alert?' },
  { id: 'live-vs-demo', label: "What's missing vs the live app?" },
  { id: 'code-access', label: 'Can I see the source code?' },
  { id: 'build-with-me', label: 'Can you build something like this for me?' },
] as const

export function AskWidget() {
  const [q, setQ] = useState('')
  const [response, setResponse] = useState<AskResponse | null>(null)

  const ask = useMutation({
    mutationFn: (query: string) => demoApi.ask(query),
    onSuccess: (data) => setResponse(data),
  })

  const submitPreset = (label: string) => {
    setQ(label)
    ask.mutate(label)
  }

  const submitFreeForm = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = q.trim()
    if (trimmed) ask.mutate(trimmed)
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="h-4 w-4 text-violet" />
          Ask the demo
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => submitPreset(p.label)}
              className="rounded-2xl px-3 py-1 text-xs text-muted-foreground shadow-extruded-sm transition-all hover:text-violet active:shadow-inset-sm"
            >
              {p.label}
            </button>
          ))}
        </div>

        <form onSubmit={submitFreeForm} className="space-y-2">
          <Textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Or type your own — demo answers a fixed set of topics."
            rows={2}
          />
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={!q.trim() || ask.isPending}>
              <Send className="mr-2 h-3 w-3" />
              {ask.isPending ? 'Asking…' : 'Ask'}
            </Button>
          </div>
        </form>

        {response && (
          <div className="space-y-3 rounded-2xl p-4 shadow-inset-sm">
            {response.match === 'miss' ? (
              <>
                <p className="text-sm text-muted-foreground">
                  The demo doesn't cover that. Try one of these instead:
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
                {response.suggestions.length > 0 && (
                  <div className="border-t border-foreground/5 pt-3">
                    <p className="mb-2 text-xs text-muted-foreground">Related:</p>
                    <div className="flex flex-wrap gap-2">
                      {response.suggestions.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => submitPreset(s.label)}
                          className="rounded-2xl px-3 py-1 text-xs text-muted-foreground shadow-extruded-sm transition-all hover:text-violet"
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
