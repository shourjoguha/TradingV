import { useState } from 'react'
import { Play, Square, AlertTriangle, CheckCircle2, Circle } from 'lucide-react'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import {
  type AdminLoopRow,
  useFireLoop,
  useAbortLoop,
} from '../../hooks/use-api'

interface Props {
  row: AdminLoopRow
}

function statusIcon(row: AdminLoopRow) {
  if (row.last_tick_at == null) return <Circle className="h-3.5 w-3.5 text-muted-foreground" />
  if (row.last_tick_ok === false)
    return <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
  return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  const now = Date.now()
  const sec = Math.max(0, Math.round((now - then) / 1000))
  if (sec < 60) return `${sec}s ago`
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`
  return `${Math.round(sec / 86400)}d ago`
}

export function ProcessRow({ row }: Props) {
  const fire = useFireLoop()
  const abort = useAbortLoop()
  const [confirming, setConfirming] = useState(false)

  const onFire = () => {
    if (row.confirm_modal_required && !confirming) {
      setConfirming(true)
      return
    }
    fire.mutate(row.loop_id)
    setConfirming(false)
  }

  return (
    <tr className="border-b last:border-b-0">
      <td className="py-2 pr-3">
        <div className="flex items-center gap-2">
          {statusIcon(row)}
          <div>
            <div className="text-sm font-medium">{row.title}</div>
            <div className="text-xs text-muted-foreground">{row.description}</div>
          </div>
        </div>
      </td>
      <td className="py-2 pr-3 text-xs">
        {row.enabled ? (
          <Badge variant="outline" className="text-emerald-600">enabled</Badge>
        ) : (
          <Badge variant="outline" className="text-muted-foreground">disabled</Badge>
        )}
        {row.cost_sensitive && (
          <Badge variant="outline" className="ml-1 text-amber-600">$</Badge>
        )}
      </td>
      <td className="py-2 pr-3 text-xs text-muted-foreground">
        {relativeTime(row.last_tick_at)}
        {row.last_duration_ms != null && (
          <span className="ml-1 opacity-60">({row.last_duration_ms}ms)</span>
        )}
      </td>
      <td className="py-2 pr-3 text-xs">
        {row.last_tick_ok === false && row.last_error && (
          <span className="text-amber-600" title={row.last_error}>
            {row.last_error.slice(0, 60)}
            {row.last_error.length > 60 ? '…' : ''}
          </span>
        )}
      </td>
      <td className="py-2 pr-3">
        <div className="flex items-center gap-1">
          {row.fire_supported && (
            <Button
              size="sm"
              variant={confirming ? 'destructive' : 'outline'}
              disabled={
                fire.isPending || row.fire_cooldown_remaining_seconds > 0
              }
              onClick={onFire}
              title={
                row.fire_cooldown_remaining_seconds > 0
                  ? `Cooldown: ${Math.ceil(row.fire_cooldown_remaining_seconds)}s`
                  : 'Fire now'
              }
            >
              <Play className="h-3 w-3 mr-1" />
              {confirming ? 'Confirm' : 'Fire'}
            </Button>
          )}
          {row.supports_abort && row.running && (
            <Button
              size="sm"
              variant="outline"
              disabled={abort.isPending}
              onClick={() => abort.mutate(row.loop_id)}
            >
              <Square className="h-3 w-3 mr-1" />
              Abort
            </Button>
          )}
        </div>
      </td>
    </tr>
  )
}
