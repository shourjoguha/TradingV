import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { AskInput } from '../components/research/AskInput'
import { AnswerCard } from '../components/research/AnswerCard'
import { HistoryList } from '../components/research/HistoryList'
import { ContextNeededBanner } from '../components/research/ContextNeededBanner'
import { SkillPicker } from '../components/research/SkillPicker'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'
import { InfoBubble } from '../components/common'
import { Loader2, Send } from 'lucide-react'
import { useResearchAsk, useResearchQueries } from '../hooks/use-api'

const PAGE_SIZE = 10

// Railway shut down 2026-05-17 — the LaptopOnlyBanner branch was removed.
// Research has always been laptop-only (vault + indexer live on laptop disk);
// see .claude/decisions/014-vault-indexer.md.

export function Research() {
  return <ResearchLaptop />
}

function ResearchLaptop() {
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<string[]>([])
  const [tickers, setTickers] = useState('')  // comma-sep
  const [filter, setFilter] = useState('all')
  const [loadedPages, setLoadedPages] = useState(1)
  const [skillSlug, setSkillSlug] = useState<string | null>(null)

  const ask = useResearchAsk()
  const queries = useResearchQueries({
    limit: loadedPages * PAGE_SIZE,
    status: filter === 'all' ? undefined : filter,
  })

  // Reset pagination when filter changes.
  useEffect(() => {
    setLoadedPages(1)
  }, [filter])

  const items = queries.data?.items ?? []
  const hasMore = items.length >= loadedPages * PAGE_SIZE

  const parseTickers = (s: string) =>
    s
      .split(',')
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean)

  const onSubmit = (opts?: { forceSkipContextGate?: boolean }) => {
    if (!query.trim()) return
    const tList = parseTickers(tickers)
    ask.mutate({
      query: query.trim(),
      hypothesis_slugs: scope.length ? scope : undefined,
      tickers: tList.length ? tList : undefined,
      force_skip_context_gate: opts?.forceSkipContextGate,
      skill_slug: skillSlug ?? undefined,
    })
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-primary" />
        Research
        <InfoBubble
          label="About Research"
          size={14}
          content={
            <>
              Stress-test active hypotheses against the vault. Single-turn — every answer
              is logged both here and as a markdown file in the vault's{' '}
              <code>Research/</code> folder.
            </>
          }
        />
      </h2>

      <Card className="relative">
        {/* Think-section card pattern (2026-05-17 — mirrors Macro
            panels): 4px identity-narrative left-bar + text-xl title +
            tight pb-1 trailing gap. Single consistent treatment across
            Research / Theses / Macro / TV-Context / The Street. */}
        <div
          aria-hidden
          className="absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl bg-identity-narrative"
        />
        <CardHeader className="pb-1 md:pb-1">
          <CardTitle className="text-xl flex items-center gap-1.5">
            Ask
            <InfoBubble
              label="About Ask"
              content="Pose a question. Optionally scope to specific hypotheses. Claude returns a verdict + supporting evidence + (sometimes) a proposed invalidator update."
            />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <SkillPicker selected={skillSlug} onChange={setSkillSlug} />
          <AskInput
            query={query}
            setQuery={setQuery}
            scope={scope}
            setScope={setScope}
            onSubmit={() => onSubmit()}
            isPending={ask.isPending}
          />
          {/* Single action row (2026-05-17 density pass): Tickers field +
              keyboard hint + Ask button live on one line. Was three
              vertical regions (AskInput action row, Tickers row, ...).
              Collapses ~80px of stacked rows into one. */}
          <div className="flex items-center gap-2 flex-wrap">
            <label
              htmlFor="research-tickers"
              className="text-xs text-muted-foreground inline-flex items-center gap-1.5 shrink-0"
            >
              Tickers
              <InfoBubble
                label="When to fill tickers"
                content={
                  <>
                    Comma-separated, optional. Required only for hypotheses flagged{' '}
                    <code>requires_tv_context</code>.
                  </>
                }
              />
            </label>
            <Input
              id="research-tickers"
              type="text"
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="AAPL, MSFT"
              className="flex-1 min-w-[180px] uppercase"
            />
            <span className="text-[11px] text-muted-foreground/70 font-mono shrink-0">
              ⌘/⌃+↵
            </span>
            <Button
              onClick={() => onSubmit()}
              disabled={!query.trim() || ask.isPending}
              className="shrink-0"
            >
              {ask.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Asking…
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Ask
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {ask.data?.status === 'needs_context' && ask.data.context_check && (
        <ContextNeededBanner
          contextCheck={ask.data.context_check}
          onSkip={() => onSubmit({ forceSkipContextGate: true })}
        />
      )}

      {ask.data && ask.data.status !== 'needs_context' && (
        <AnswerCard response={ask.data} />
      )}

      <Card className="relative">
        <div
          aria-hidden
          className="absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl bg-identity-narrative"
        />
        <CardHeader className="pb-1 md:pb-1">
          <CardTitle className="text-xl flex items-center gap-1.5">
            History
            <InfoBubble label="About History" content="Expand any row for the full answer." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {queries.isLoading ? (
            <div className="text-xs text-muted-foreground">Loading…</div>
          ) : (
            <HistoryList
              items={items}
              filter={filter}
              setFilter={setFilter}
              hasMore={hasMore}
              loading={queries.isFetching}
              onLoadMore={() => setLoadedPages((p) => p + 1)}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
