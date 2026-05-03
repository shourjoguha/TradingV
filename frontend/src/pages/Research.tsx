import { useEffect, useState } from 'react'
import { Laptop, Sparkles } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { AskInput } from '../components/research/AskInput'
import { AnswerCard } from '../components/research/AnswerCard'
import { HistoryList } from '../components/research/HistoryList'
import { useResearchAsk, useResearchQueries } from '../hooks/use-api'
import { useBackend } from '../hooks/use-backend'

const PAGE_SIZE = 10

function ResearchLaptopOnlyBanner() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Sparkles className="h-5 w-5 text-violet" />
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">Research</h2>
          <p className="text-muted-foreground text-sm">
            Stress-test active hypotheses against the vault.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Laptop className="h-4 w-4 text-violet" />
            Research is laptop-only
          </CardTitle>
          <CardDescription>
            The knowledge vault and its indexer live on your laptop. Railway has no vault to query
            against and no Obsidian for the markdown approval flow.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Switch the backend toggle (top-right) to <strong>Laptop</strong> to ask a question or
            review past stress-tests.
          </p>
          <p className="text-xs">
            Why this is a deliberate split: vault content is curated on your local disk; replicating
            it to Railway would require a second indexer + embedding cache + a non-markdown
            approval path. See <code>.claude/decisions/014-vault-indexer.md</code> and{' '}
            <code>015-research-stress-test.md</code>.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export function Research() {
  const { backendId } = useBackend()
  if (backendId === 'railway') return <ResearchLaptopOnlyBanner />

  return <ResearchLaptop />
}

function ResearchLaptop() {
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<string[]>([])
  const [filter, setFilter] = useState('all')
  const [loadedPages, setLoadedPages] = useState(1)

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

  const onSubmit = () => {
    if (!query.trim()) return
    ask.mutate({
      query: query.trim(),
      hypothesis_slugs: scope.length ? scope : undefined,
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Sparkles className="h-5 w-5 text-violet" />
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">Research</h2>
          <p className="text-muted-foreground text-sm">
            Stress-test active hypotheses against the vault. Single-turn — every answer is logged
            both here and as a markdown file in the vault's <code>Research/</code> folder.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ask</CardTitle>
          <CardDescription>
            Pose a question. Optionally scope to specific hypotheses. Claude returns a verdict +
            supporting evidence + (sometimes) a proposed invalidator update.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AskInput
            query={query}
            setQuery={setQuery}
            scope={scope}
            setScope={setScope}
            onSubmit={onSubmit}
            isPending={ask.isPending}
          />
        </CardContent>
      </Card>

      {ask.data && <AnswerCard response={ask.data} />}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">History</CardTitle>
          <CardDescription>Expand any row for the full answer.</CardDescription>
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
