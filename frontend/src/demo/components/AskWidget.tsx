import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Sparkles, Send } from 'lucide-react'
import { demoApi, type AskResponse } from '../api'
import { Card } from '../../components/ui/card'
import { Button } from '../../components/ui/button'
import { Textarea } from '../../components/ui/textarea'

const PRESETS = [
  { id: 'what-is-this', label: 'What is this app?' },
  { id: 'how-accurate', label: 'How accurate are the predictions?' },
  { id: 'what-signals', label: 'How do opportunities get generated?' },
  { id: 'trade-attribution', label: 'How is P&L attributed to rules?' },
  { id: 'model-used', label: 'What model produces forecasts?' },
  { id: 'data-sources', label: 'What data sources feed this?' },
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
    if (q.trim()) ask.mutate(q.trim())
  }

  return (
    <Card className="space-y-4 border-violet/20 bg-zinc-900/40 p-5">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet" />
        <h3 className="font-medium">Ask the demo</h3>
      </div>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => submitPreset(p.label)}
            className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs text-zinc-300 transition hover:border-violet hover:text-violet"
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
          className="bg-zinc-950"
        />
        <div className="flex justify-end">
          <Button
            type="submit"
            size="sm"
            disabled={!q.trim() || ask.isPending}
            onClick={(e) => {
              if (!q.trim()) return
              e.preventDefault()
              ask.mutate(q.trim())
            }}
          >
            <Send className="mr-2 h-3 w-3" />
            {ask.isPending ? 'Asking…' : 'Ask'}
          </Button>
        </div>
      </form>

      {response && (
        <div className="space-y-2 rounded-md border border-zinc-800 bg-zinc-950/60 p-4">
          {response.match === 'miss' ? (
            <>
              <p className="text-sm text-zinc-400">
                The demo doesn't cover that. Try one of these instead:
              </p>
              <div className="flex flex-wrap gap-2">
                {response.suggestions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => submitPreset(s.label)}
                    className="rounded-full border border-violet/40 px-3 py-1 text-xs text-violet hover:bg-violet/10"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-zinc-100">
                  {response.answer?.title}
                </p>
                <span className="rounded-full bg-violet/10 px-2 py-0.5 text-xs text-violet">
                  {response.match}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-zinc-300">
                {response.answer?.body}
              </p>
              {response.suggestions.length > 0 && (
                <div className="border-t border-zinc-800 pt-2">
                  <p className="mb-2 text-xs text-zinc-500">Related:</p>
                  <div className="flex flex-wrap gap-2">
                    {response.suggestions.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => submitPreset(s.label)}
                        className="rounded-full border border-zinc-800 px-3 py-1 text-xs text-zinc-400 hover:border-violet hover:text-violet"
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

    </Card>
  )
}
