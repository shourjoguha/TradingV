import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Camera, Laptop, Lightbulb, StickyNote, Calendar } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { useBackend } from '../hooks/use-backend'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Textarea } from '../components/ui/textarea'
import { Skeleton } from '../components/ui/skeleton'
import { ScreenshotUploadModal } from '../components/tv-context/ScreenshotUploadModal'
import { ContextItemCard } from '../components/tv-context/ContextItemCard'
import {
  useTVContextByTicker,
  useTVVisionSpend,
  useIngestTVNote,
  useIngestTVIdea,
  useIngestTVEvent,
} from '../hooks/use-api'

function currentMonth(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function TVContextLaptopOnlyBanner() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Camera className="h-5 w-5 text-violet" />
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">TV Context</h2>
          <p className="text-muted-foreground text-sm">
            TradingView signals — webhooks, screenshots, notes, ideas, events.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Laptop className="h-4 w-4 text-violet" />
            TV Context is laptop-only
          </CardTitle>
          <CardDescription>
            Screenshots are stored as sidecar markdown in your local Obsidian vault, which lives on
            your laptop. Railway has no vault to read or write into.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Switch the backend toggle (top-right) to <strong>Laptop</strong> to drop screenshots,
            attach notes, or browse the per-ticker context feed.
          </p>
          <p className="text-xs">
            Webhook / note / idea / event rows still replicate to Railway via the sync outbox so
            retrieval works cross-machine — only this UI surface is gated. See{' '}
            <code>.claude/decisions/016-tv-context-no-browser-automation.md</code>.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export function TVContextInbox() {
  const { backendId } = useBackend()
  if (backendId === 'railway') return <TVContextLaptopOnlyBanner />
  return <TVContextInboxLaptop />
}

function TVContextInboxLaptop() {
  const { ticker: routeTicker } = useParams<{ ticker?: string }>()
  const navigate = useNavigate()
  const [tickerInput, setTickerInput] = useState(routeTicker?.toUpperCase() ?? '')
  const [showScreenshot, setShowScreenshot] = useState(false)
  const [includeExpired, setIncludeExpired] = useState(false)

  const ticker = (routeTicker || tickerInput).toUpperCase().trim() || null
  const items = useTVContextByTicker(ticker, { includeExpired })
  const monthSpend = useTVVisionSpend(currentMonth())

  const onSearch = () => {
    const t = tickerInput.trim().toUpperCase()
    if (t) navigate(`/tv-context/${t}`)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3">
            <Camera className="h-5 w-5 text-violet" />
            <h2 className="text-2xl font-heading font-semibold tracking-tight">
              TV Context
            </h2>
          </div>
          <p className="text-muted-foreground text-sm mt-1">
            TradingView signals — webhooks, screenshots, notes, ideas, events.
          </p>
        </div>

        <Card className="px-4 py-2 text-sm">
          <div className="text-xs text-muted-foreground">Vision spend ({currentMonth()})</div>
          <div className="font-medium">
            {monthSpend.isLoading
              ? '…'
              : `$${(monthSpend.data?.total_usd ?? 0).toFixed(3)} · ${
                  monthSpend.data?.call_count ?? 0
                } calls`}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Lookup ticker</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 items-end flex-wrap">
            <div className="flex-1 min-w-[160px]">
              <Label htmlFor="ticker-search" className="text-xs">
                Ticker
              </Label>
              <Input
                id="ticker-search"
                value={tickerInput}
                onChange={(e) => setTickerInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && onSearch()}
                placeholder="AAPL"
                className="mt-1 uppercase"
              />
            </div>
            <Button onClick={onSearch}>Search</Button>
            <Button
              variant="outline"
              onClick={() => setIncludeExpired((v) => !v)}
            >
              {includeExpired ? 'Hide expired' : 'Show expired'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {ticker ? (
        <>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setShowScreenshot(true)} className="gap-2">
              <Camera className="h-4 w-4" /> Screenshot
            </Button>
            <NoteIngestForm ticker={ticker} />
            <IdeaIngestForm ticker={ticker} />
            <EventIngestForm ticker={ticker} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Recent context for {ticker}
              </CardTitle>
              <CardDescription>
                {items.data?.length ?? 0} items
                {includeExpired ? ' (incl. expired)' : ' active'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {items.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : !items.data?.length ? (
                <p className="text-sm text-muted-foreground">
                  No context yet. Drop a screenshot, paste a note, or send a Pine
                  webhook to <code>/webhook</code> with payload{' '}
                  <code>{`{"source":"tradingview"}`}</code>.
                </p>
              ) : (
                items.data.map((item) => (
                  <ContextItemCard key={item.id} item={item} />
                ))
              )}
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Enter a ticker above to view its context feed.
          </CardContent>
        </Card>
      )}

      <ScreenshotUploadModal
        open={showScreenshot}
        onOpenChange={setShowScreenshot}
        defaultTicker={ticker ?? undefined}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Note ingest popover-form
// ---------------------------------------------------------------------------

function NoteIngestForm({ ticker }: { ticker: string }) {
  const [open, setOpen] = useState(false)
  const [body, setBody] = useState('')
  const ingest = useIngestTVNote()

  const onSubmit = async () => {
    if (!body.trim()) return
    try {
      await ingest.mutateAsync({ ticker, body: body.trim() })
      setBody('')
      setOpen(false)
    } catch {
      /* toast in hook */
    }
  }

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)} className="gap-2">
        <StickyNote className="h-4 w-4" /> Note
      </Button>
    )
  }
  return (
    <Card className="w-full max-w-lg">
      <CardContent className="p-3 space-y-2">
        <Label className="text-xs">Note for {ticker}</Label>
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="What did you observe?"
          rows={3}
        />
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={!body.trim() || ingest.isPending}>
            {ingest.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Idea ingest popover-form
// ---------------------------------------------------------------------------

function IdeaIngestForm({ ticker }: { ticker: string }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [summary, setSummary] = useState('')
  const ingest = useIngestTVIdea()

  const onSubmit = async () => {
    if (!url.trim()) return
    try {
      await ingest.mutateAsync({
        ticker,
        url: url.trim(),
        summary: summary.trim() || undefined,
      })
      setUrl('')
      setSummary('')
      setOpen(false)
    } catch {
      /* toast in hook */
    }
  }

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)} className="gap-2">
        <Lightbulb className="h-4 w-4" /> Idea
      </Button>
    )
  }
  return (
    <Card className="w-full max-w-lg">
      <CardContent className="p-3 space-y-2">
        <Label className="text-xs">TradingView Idea URL</Label>
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.tradingview.com/chart/…"
        />
        <Label className="text-xs">Summary</Label>
        <Textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="What's this idea about?"
          rows={2}
        />
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={!url.trim() || ingest.isPending}>
            {ingest.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Event ingest popover-form
// ---------------------------------------------------------------------------

function EventIngestForm({ ticker }: { ticker: string }) {
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [date, setDate] = useState('')
  const ingest = useIngestTVEvent()

  const onSubmit = async () => {
    if (!label.trim() || !date) return
    try {
      await ingest.mutateAsync({ ticker, label: label.trim(), event_date: date })
      setLabel('')
      setDate('')
      setOpen(false)
    } catch {
      /* toast in hook */
    }
  }

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)} className="gap-2">
        <Calendar className="h-4 w-4" /> Event
      </Button>
    )
  }
  return (
    <Card className="w-full max-w-lg">
      <CardContent className="p-3 space-y-2">
        <Label className="text-xs">Label</Label>
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Q3 earnings, FOMC, etc."
        />
        <Label className="text-xs">Date</Label>
        <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={onSubmit}
            disabled={!label.trim() || !date || ingest.isPending}
          >
            {ingest.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
