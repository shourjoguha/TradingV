import { useState } from 'react'
import { Search } from 'lucide-react'
import {
  useTickerReviewQueue,
  useResolveTickerReview,
  useBoards,
} from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import type { TickerReviewRead, TickerReviewAction } from '../../lib/types'

/**
 * Phase D — unknown-ticker review surface for the Today landing.
 *
 * Lists tickers Stage 1 of the video-vision pipeline saw in operator
 * channels but that aren't in roster / boards / The Street yet.
 * Backend already filters `times_seen >= 2` so single-mention noise
 * stays in the DB but doesn't reach the strip.
 *
 * Hidden when the queue is empty — no chrome leaks.
 */
const ROW_CAP = 10

export function TickerReviewStrip() {
  const queue = useTickerReviewQueue({ status: 'pending', limit: 50 })
  const boards = useBoards()
  const resolve = useResolveTickerReview()
  const [boardChoice, setBoardChoice] = useState<Record<number, string>>({})

  if (queue.isLoading) return null
  const items = queue.data?.items ?? []
  if (items.length === 0) return null

  const visible = items.slice(0, ROW_CAP)
  const overflow = Math.max(0, items.length - visible.length)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Search className="h-4 w-4 text-violet" />
          Tickers to review ({items.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {visible.map((entry) => (
          <TickerReviewRow
            key={entry.id}
            entry={entry}
            isWorking={resolve.isPending && resolve.variables?.id === entry.id}
            boardId={boardChoice[entry.id] ?? ''}
            onBoardChange={(id) =>
              setBoardChoice((s) => ({ ...s, [entry.id]: id }))
            }
            boards={boards.data?.items ?? []}
            onResolve={(action) => {
              const body: { action: TickerReviewAction; board_id?: string } = {
                action,
              }
              if (action === 'add_to_board') {
                const bid = boardChoice[entry.id]
                if (!bid) return
                body.board_id = bid
              }
              resolve.mutate({ id: entry.id, body })
            }}
          />
        ))}
        {overflow > 0 && (
          <div className="text-xs text-muted-foreground pt-1">
            +{overflow} more — see vault digest
            <code className="px-1 ml-1 text-[10px] bg-background rounded">
              Topics/_ticker-review-queue.md
            </code>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

interface RowProps {
  entry: TickerReviewRead
  isWorking: boolean
  boardId: string
  onBoardChange: (id: string) => void
  boards: { id: string; name: string }[]
  onResolve: (action: TickerReviewAction) => void
}

function TickerReviewRow({
  entry,
  isWorking,
  boardId,
  onBoardChange,
  boards,
  onResolve,
}: RowProps) {
  const channels = entry.channels.join(', ') || 'unknown channel'
  const snippet =
    entry.recent_caption_snippets[entry.recent_caption_snippets.length - 1] ||
    ''
  const prevDismiss = entry.previously_dismissed_at
    ? new Date(entry.previously_dismissed_at).toLocaleDateString()
    : null

  return (
    <div className="rounded-2xl shadow-inset-sm bg-background px-3 py-2 space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold tracking-wide">
          {entry.ticker}
        </span>
        <span className="text-xs text-muted-foreground">
          seen {entry.times_seen}× across {channels}
        </span>
        {prevDismiss && (
          <Badge variant="outline" className="text-[10px] shrink-0">
            previously dismissed {prevDismiss}
          </Badge>
        )}
      </div>
      {snippet && (
        <div className="text-xs text-muted-foreground italic line-clamp-2">
          “{snippet}”
        </div>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        <Button
          size="sm"
          className="h-7 px-3 text-xs"
          disabled={isWorking}
          onClick={() => onResolve('add_to_roster')}
        >
          Add to roster
        </Button>
        <div className="flex items-center gap-1">
          <Select value={boardId} onValueChange={onBoardChange}>
            <SelectTrigger className="h-7 w-40 text-xs">
              <SelectValue placeholder="Pick board…" />
            </SelectTrigger>
            <SelectContent>
              {boards.length === 0 ? (
                <SelectItem value="__none__" disabled>
                  No boards yet
                </SelectItem>
              ) : (
                boards.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.name}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            disabled={isWorking || !boardId}
            onClick={() => onResolve('add_to_board')}
          >
            Add
          </Button>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-3 text-xs ml-auto"
          disabled={isWorking}
          onClick={() => onResolve('dismiss')}
        >
          Dismiss
        </Button>
      </div>
    </div>
  )
}
