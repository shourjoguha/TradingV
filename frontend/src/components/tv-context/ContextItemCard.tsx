import { useState } from 'react'
import {
  Bell,
  Calendar,
  Camera,
  ExternalLink,
  Lightbulb,
  StickyNote,
  Trash2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { Card, CardContent } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import type { TVContextItem, TVContextKind } from '../../lib/types'
import { useArchiveTVContext } from '../../hooks/use-api'

const KIND_ICONS: Record<TVContextKind, typeof Bell> = {
  webhook: Bell,
  screenshot: Camera,
  note: StickyNote,
  idea: Lightbulb,
  event: Calendar,
}

/**
 * Provenance color per source (2026-05-17 color taxonomy). Distinct
 * per-kind hue gives the operator a pre-attentive "where did this come
 * from?" channel on the timeline. Migrated from raw Tailwind utilities
 * (text-amber-500 etc.) to on-palette tokens so the colors compose w/
 * the rest of the matte-bold scheme.
 */
const KIND_COLORS: Record<TVContextKind, string> = {
  webhook: 'text-warning-fg',          // alert-like
  screenshot: 'text-primary',           // operator capture → primary action color
  note: 'text-success-fg',             // hand-typed observation
  idea: 'text-identity-liquidity',     // generative (slate-blue, was sky-500)
  event: 'text-danger-fg',             // time-bound triggering
}

interface ContextItemCardProps {
  item: TVContextItem
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function summarize(item: TVContextItem): string {
  const p = item.payload as Record<string, unknown>
  switch (item.kind) {
    case 'webhook':
      return String(p.alert_type ?? 'webhook')
    case 'note':
      return String(p.body ?? p.preview ?? '').slice(0, 200)
    case 'idea':
      return String(p.summary ?? p.url ?? 'idea')
    case 'event':
      return `${p.label ?? 'event'} — ${p.event_date ?? ''}`
    case 'screenshot':
      return String(p.note ?? 'chart screenshot')
  }
}

export function ContextItemCard({ item }: ContextItemCardProps) {
  const [expanded, setExpanded] = useState(false)
  const archive = useArchiveTVContext()
  const Icon = KIND_ICONS[item.kind]
  const payload = item.payload as Record<string, unknown>
  const vision = (payload.vision ?? null) as Record<string, unknown> | null
  const dedupeCount = Number(payload.dedupe_count ?? 1)

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-3">
        <div className="flex items-start gap-3">
          <Icon className={`h-4 w-4 mt-1 shrink-0 ${KIND_COLORS[item.kind]}`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm font-medium">
                {item.ticker ?? '—'}
              </span>
              <Badge variant="secondary" className="text-xs uppercase">
                {item.kind}
              </Badge>
              {dedupeCount > 1 && (
                <Badge variant="outline" className="text-xs">
                  ×{dedupeCount}
                </Badge>
              )}
              {item.status !== 'active' && (
                <Badge variant="outline" className="text-xs">
                  {item.status}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground ml-auto">
                {formatTimestamp(item.captured_at)}
              </span>
            </div>

            <div className="mt-1 text-sm text-foreground/90 break-words">
              {summarize(item)}
            </div>

            {item.kind === 'idea' && payload.url ? (
              <a
                href={String(payload.url)}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-xs text-sky-500 hover:underline"
              >
                <ExternalLink className="h-3 w-3" />
                open on TradingView
              </a>
            ) : null}

            {(vision || item.vault_path) && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                {expanded ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                {expanded ? 'hide details' : 'show details'}
              </button>
            )}

            {expanded && (
              <div className="mt-2 space-y-2 text-xs">
                {item.vault_path && (
                  <div className="font-mono text-muted-foreground break-all">
                    {item.vault_path}
                  </div>
                )}
                {vision && (
                  <div className="rounded border bg-muted/40 p-2 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">Vision summary</span>
                      {typeof vision.cost_usd === 'number' && (
                        <span className="text-muted-foreground">
                          (${(vision.cost_usd as number).toFixed(4)})
                        </span>
                      )}
                    </div>
                    <pre className="whitespace-pre-wrap font-sans text-foreground/90">
                      {String(vision.summary_md ?? '(no summary)')}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>

          {item.status === 'active' && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 shrink-0"
              onClick={() => archive.mutate(item.id)}
              title="Archive (drops heavy payload, keeps tombstone)"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
