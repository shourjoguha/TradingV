import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
import { useRetentionStatus, usePurgeRetention } from '../../hooks/use-api'

function PurgeButton({ keyName }: { keyName: string }) {
  const purge = usePurgeRetention()
  const [step, setStep] = useState<'idle' | 'confirm'>('idle')

  const onClick = () => {
    if (step === 'idle') {
      // Preview step.
      purge.mutate({ key: keyName, confirm: false })
      setStep('confirm')
      return
    }
    purge.mutate({ key: keyName, confirm: true })
    setStep('idle')
  }

  return (
    <Button
      size="sm"
      variant={step === 'confirm' ? 'destructive' : 'outline'}
      disabled={purge.isPending}
      onClick={onClick}
    >
      {step === 'confirm' ? 'Confirm purge' : 'Purge'}
    </Button>
  )
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  const sec = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`
  return `${Math.round(sec / 86400)}d ago`
}

export function RetentionTab() {
  const { data, isLoading } = useRetentionStatus()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Retention</CardTitle>
        <CardDescription>
          Per-class TTL + manual purge (capped 5000 rows per click). Approved + pending
          research queries kept forever; dismissed/error TTLs configurable.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-32 w-full" />}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Class</th>
                  <th className="py-2 pr-3">Rows</th>
                  <th className="py-2 pr-3">Oldest</th>
                  <th className="py-2 pr-3">TTL</th>
                  <th className="py-2 pr-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.key} className="border-b last:border-b-0 align-top">
                    <td className="py-2 pr-3">
                      <div className="text-sm font-medium">{row.title}</div>
                      <div className="text-[10px] text-muted-foreground">{row.key}</div>
                    </td>
                    <td className="py-2 pr-3 text-sm">
                      {row.row_count}
                      {row.row_count_extra && (
                        <div className="text-[10px] text-muted-foreground">
                          {Object.entries(row.row_count_extra)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(' · ')}
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {relativeTime(row.oldest_at)}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {typeof row.ttl_days === 'number' ? `${row.ttl_days}d` : row.ttl_days}
                      {row.ttl_days_extra && (
                        <div className="text-[10px]">
                          {Object.entries(row.ttl_days_extra)
                            .map(([k, v]) => `${k}: ${typeof v === 'number' ? `${v}d` : v}`)
                            .join(' · ')}
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <PurgeButton keyName={row.key} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
