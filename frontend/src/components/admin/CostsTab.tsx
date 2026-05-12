import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { Button } from '../ui/button'
import {
  useCostsMonthly,
  useCostsRecent,
  useAdminSettings,
  useUpdateAdminSetting,
} from '../../hooks/use-api'

function CapProgress({ total, cap }: { total: number; cap: number }) {
  if (!cap || cap <= 0) return null
  const pct = Math.min(100, Math.round((total / cap) * 100))
  const danger = pct >= 80
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span>Monthly cap</span>
        <span>
          ${total.toFixed(2)} / ${cap.toFixed(2)}{' '}
          <span className={danger ? 'text-amber-600' : 'text-muted-foreground'}>
            ({pct}%)
          </span>
        </span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={
            'h-full ' +
            (pct >= 100
              ? 'bg-rose-500'
              : pct >= 80
              ? 'bg-amber-500'
              : 'bg-emerald-500')
          }
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function VisionMonthlyToggle() {
  const { data } = useAdminSettings()
  const update = useUpdateAdminSetting()
  const enabled = data?.items?.['tv_context.vision_enabled_this_month']
  if (data == null) return null
  return (
    <div className="flex items-center justify-between rounded-md border p-3 text-sm">
      <div>
        <div className="font-medium">TV Context vision</div>
        <div className="text-xs text-muted-foreground">
          Disables Claude vision summaries on screenshot ingest for the rest of the month.
        </div>
      </div>
      <Button
        size="sm"
        variant={enabled ? 'outline' : 'destructive'}
        disabled={update.isPending}
        onClick={() =>
          update.mutate({
            key: 'tv_context.vision_enabled_this_month',
            value: !enabled,
          })
        }
      >
        {enabled ? 'Enabled — disable' : 'Disabled — enable'}
      </Button>
    </div>
  )
}

function MiniBarChart({ items }: { items: { date: string; research_usd: number; vision_usd: number }[] }) {
  if (!items.length) return null
  const max = Math.max(0.01, ...items.map((i) => i.research_usd + i.vision_usd))
  return (
    <div className="space-y-1">
      <div className="flex items-end gap-px h-24">
        {items.map((item) => {
          const total = item.research_usd + item.vision_usd
          const pct = (total / max) * 100
          const research_pct = total > 0 ? (item.research_usd / total) * pct : 0
          const vision_pct = total > 0 ? (item.vision_usd / total) * pct : 0
          return (
            <div
              key={item.date}
              className="flex-1 flex flex-col-reverse"
              title={`${item.date}: research $${item.research_usd.toFixed(3)} + vision $${item.vision_usd.toFixed(3)}`}
            >
              <div className="bg-violet" style={{ height: `${research_pct}%` }} />
              <div className="bg-emerald-500" style={{ height: `${vision_pct}%` }} />
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
        <span><span className="inline-block w-2 h-2 bg-violet mr-1"/>research</span>
        <span><span className="inline-block w-2 h-2 bg-emerald-500 mr-1"/>vision</span>
      </div>
    </div>
  )
}

export function CostsTab() {
  const monthly = useCostsMonthly()
  const recent = useCostsRecent(30)
  const settings = useAdminSettings()

  const cap = Number(settings.data?.items?.['anthropic.monthly_cap_usd'] ?? 0)
  const total = monthly.data?.total_usd ?? 0
  const killed = settings.data?.items?.['anthropic.kill_switch_active'] ?? false

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">This month</CardTitle>
          <CardDescription>
            Anthropic spend across Research stress-tests + TV vision summaries.
            Cache TTL 5 min. Cap auto-flips the kill-switch at 100%.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {monthly.isLoading && <Skeleton className="h-12 w-full" />}
          {monthly.data && (
            <>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <div className="text-muted-foreground text-[10px] uppercase">Total</div>
                  <div className="text-2xl font-semibold">${total.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground text-[10px] uppercase">Research</div>
                  <div className="text-lg font-medium">
                    ${monthly.data.research_total_usd.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {monthly.data.research_count} queries
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground text-[10px] uppercase">Vision</div>
                  <div className="text-lg font-medium">
                    ${monthly.data.vision_total_usd.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {monthly.data.vision_count} screenshots
                  </div>
                </div>
              </div>
              <CapProgress total={total} cap={cap} />
              {killed && (
                <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-600">
                  Kill-switch active — Claude calls refuse. Toggle off via Cadences tab or raise the cap.
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Last 30 days</CardTitle>
        </CardHeader>
        <CardContent>
          {recent.isLoading && <Skeleton className="h-24 w-full" />}
          {recent.data && <MiniBarChart items={recent.data.items} />}
        </CardContent>
      </Card>

      <VisionMonthlyToggle />
    </div>
  )
}
