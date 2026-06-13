import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  useBoards,
  useBoard,
  useCreateBoard,
  useDeleteBoard,
  useAddTickerToBoard,
  useRemoveTickerFromBoard,
  useMoveTicker,
} from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { EmptyState } from '../components/common'
import { Plus, Trash2, ExternalLink, ArrowRight, X } from 'lucide-react'

// Open the symbol on TradingView in a new tab — operator's chosen
// brokerage / chart surface, per the brainstorm.
function tradingViewHref(symbol: string): string {
  return `https://www.tradingview.com/symbols/${encodeURIComponent(symbol)}/`
}

function fmtDeltaPct(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function fmtClose(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v >= 1000) return v.toFixed(0)
  return v.toFixed(2)
}

export function Watchlists() {
  // The legacy `/watchlists/:boardId` route now redirects to `/watchlist/boards`,
  // so URL-driven board selection would create a redirect loop with the
  // consolidated page. Track active board in local state instead.
  const { boardId: paramBoardId } = useParams<{ boardId?: string }>()
  const { data: boards } = useBoards()
  const items = boards?.items ?? []
  const [selectedId, setSelectedId] = useState<string>(paramBoardId ?? '')

  const activeId = selectedId || paramBoardId || items[0]?.id || ''
  const active = useBoard(activeId)

  // Auto-pick the first board once the list loads. Local state — no router
  // navigate (would loop against the legacy `/watchlists/:boardId` redirect).
  useEffect(() => {
    if (!selectedId && items.length > 0) {
      setSelectedId(items[0].id)
    }
  }, [selectedId, items])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <NewBoardButton />
      </div>

      {/* Board selector — chips. Empty state when none. */}
      {items.length === 0 ? (
        <EmptyState
          title="No watchlists yet"
          description="Create your first list — group tickers by thesis (e.g. 'Costa-mentioned', 'AI-resilient SaaS', 'Reshoring plays')."
        />
      ) : (
        // Board picker chips — sized to match the Opportunities tab
        // controls (px-4 py-2 text-sm font-medium rounded-xl) so the
        // Decide section's two adjacent control vocabularies read
        // consistent. Was previously px-3 py-1.5 text-xs — too dainty
        // for the most-clicked nav in Decide.
        <div className="flex flex-wrap gap-2">
          {items.map((b) => {
            const selected = b.id === activeId
            return (
              <button
                key={b.id}
                type="button"
                onClick={() => setSelectedId(b.id)}
                className={[
                  'px-4 py-2 rounded-xl text-sm font-medium transition-all',
                  selected
                    ? 'bg-card text-foreground shadow-extruded-sm'
                    : 'bg-background text-muted-foreground shadow-inset-sm hover:text-foreground',
                ].join(' ')}
              >
                {b.name}
                <span className="ml-2 font-mono text-xs opacity-60 tabular-nums">
                  {b.ticker_count}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {/* Active board detail */}
      {active.data && (
        <BoardDetailView
          boardId={activeId}
          name={active.data.name}
          description={active.data.description}
          tickers={active.data.tickers}
          allBoards={items}
          onDeleted={() => setSelectedId('')}
        />
      )}
    </div>
  )
}

function NewBoardButton() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useCreateBoard()

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="h-4 w-4 mr-1" />
          New watchlist
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New watchlist</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Costa-mentioned"
            />
          </div>
          <div className="space-y-2">
            <Label>Description (optional)</Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What unifies this list?"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              if (!name.trim()) return
              create.mutate(
                { name: name.trim(), description: description.trim() || undefined },
                {
                  onSuccess: () => {
                    setOpen(false)
                    setName('')
                    setDescription('')
                  },
                },
              )
            }}
            disabled={create.isPending}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface BoardDetailViewProps {
  boardId: string
  name: string
  description: string | null
  tickers: Array<{
    ticker: string
    notes: string | null
    last_close: number | null
    last_close_at: string | null
    pct_1w: number | null
    quote_fetched_at: string | null
  }>
  allBoards: Array<{ id: string; name: string }>
  onDeleted: () => void
}

function BoardDetailView({
  boardId,
  name,
  description,
  tickers,
  allBoards,
  onDeleted,
}: BoardDetailViewProps) {
  const [tickerInput, setTickerInput] = useState('')
  const addTicker = useAddTickerToBoard()
  const removeTicker = useRemoveTickerFromBoard()
  const moveTicker = useMoveTicker()
  const deleteBoard = useDeleteBoard()
  const moveTargets = useMemo(
    () => allBoards.filter((b) => b.id !== boardId),
    [allBoards, boardId],
  )

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">{name}</CardTitle>
            {description && (
              <CardDescription className="text-xs mt-0.5">{description}</CardDescription>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              if (
                confirm(
                  `Delete watchlist "${name}"? Tickers will be removed from this list (but stay in the registry).`,
                )
              ) {
                deleteBoard.mutate(boardId, {
                  onSuccess: onDeleted,
                })
              }
            }}
            title="Delete this watchlist"
            aria-label="Delete watchlist"
          >
            <Trash2 className="h-4 w-4 text-muted-foreground hover:text-danger" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Add-ticker control */}
        <div className="flex items-center gap-2">
          <Input
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value)}
            placeholder="Add ticker (e.g. NVDA)"
            className="font-mono uppercase max-w-[240px]"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const t = tickerInput.trim().toUpperCase()
                if (!t) return
                addTicker.mutate(
                  { boardId, ticker: t },
                  { onSuccess: () => setTickerInput('') },
                )
              }
            }}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!tickerInput.trim() || addTicker.isPending}
            onClick={() => {
              const t = tickerInput.trim().toUpperCase()
              if (!t) return
              addTicker.mutate(
                { boardId, ticker: t },
                { onSuccess: () => setTickerInput('') },
              )
            }}
          >
            Add
          </Button>
        </div>

        {/* Ticker rows */}
        {tickers.length === 0 ? (
          <EmptyState
            bare
            title="No tickers yet"
            description="Add a symbol above. Hit Enter to commit."
          />
        ) : (
          <div className="space-y-1">
            {tickers.map((t) => {
              const pct = t.pct_1w
              const pctClass =
                pct == null
                  ? 'text-muted-foreground'
                  : pct > 0
                    ? 'text-success'
                    : pct < 0
                      ? 'text-danger'
                      : 'text-muted-foreground'
              return (
                <div
                  key={t.ticker}
                  className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-background shadow-inset-sm"
                >
                  <a
                    href={tradingViewHref(t.ticker)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 min-w-0 flex-1 group"
                    title="Open on TradingView"
                  >
                    <span className="font-mono font-semibold text-sm">{t.ticker}</span>
                    <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    {t.notes && (
                      <span className="text-xs text-muted-foreground truncate ml-2">
                        — {t.notes}
                      </span>
                    )}
                  </a>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs font-mono tabular-nums text-foreground">
                      ${fmtClose(t.last_close)}
                    </span>
                    <span className={`text-xs font-mono tabular-nums w-16 text-right ${pctClass}`}>
                      {fmtDeltaPct(t.pct_1w)}
                    </span>
                    {/* Move-to-other-list dropdown (only if there's a target) */}
                    {moveTargets.length > 0 && (
                      <Select
                        onValueChange={(targetId) => {
                          if (!targetId) return
                          moveTicker.mutate({
                            sourceBoardId: boardId,
                            targetBoardId: targetId,
                            ticker: t.ticker,
                          })
                        }}
                      >
                        <SelectTrigger className="h-7 w-[42px] px-2 text-xs">
                          <ArrowRight className="h-3 w-3" />
                        </SelectTrigger>
                        <SelectContent>
                          {moveTargets.map((b) => (
                            <SelectItem key={b.id} value={b.id} className="text-xs">
                              {b.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        removeTicker.mutate({ boardId, ticker: t.ticker })
                      }
                      title="Remove from this watchlist"
                      aria-label={`Remove ${t.ticker}`}
                      className="h-7 w-7"
                    >
                      <X className="h-3.5 w-3.5 text-muted-foreground hover:text-danger" />
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default Watchlists
