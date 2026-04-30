import {
  useSchedule,
  useAnalysisJobs,
  useFireNow,
  useQueueStats,
  useQueue,
} from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { Play, Clock, Layers } from 'lucide-react'
import { Link } from 'react-router-dom'
import { RegimeStrip } from '../components/dashboard/RegimeStrip'
import { LatestOpportunity } from '../components/dashboard/LatestOpportunity'
import { AccuracyTile } from '../components/dashboard/AccuracyTile'

export function Dashboard() {
  const { data: schedule, isLoading: isLoadingSchedule } = useSchedule()
  const { data: jobs, isLoading: isLoadingJobs } = useAnalysisJobs({ limit: 5 })
  const { mutate: fireNow, isPending: isFiring } = useFireNow()
  const { data: queueStats } = useQueueStats()
  const { data: queue } = useQueue({ status: 'pending', limit: 5 })
  const { data: runningQueue } = useQueue({ status: 'running', limit: 1 })
  const runningItem = runningQueue?.items[0]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Overview
          </h2>
          <p className="text-muted-foreground text-sm">
            Morning glance: regime context, latest opportunity, accuracy snapshot, and what's running.
          </p>
        </div>
        <Button onClick={() => fireNow()} disabled={isFiring || !schedule?.enabled} size="lg">
          <Play className="mr-2 h-4 w-4" />
          Run Now
        </Button>
      </div>

      {/* Row 1 — Regime context (one tile per axis, 1y delta + sparkline). */}
      <RegimeStrip />

      {/* Row 2 — Latest opportunity (wide) + Accuracy + Schedule status. */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="lg:col-span-2">
          <LatestOpportunity />
        </div>
        <AccuracyTile />
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4 text-violet" />
              Schedule
            </CardTitle>
            <Link to="/schedule" className="text-xs text-muted-foreground hover:text-violet">
              Detail
            </Link>
          </CardHeader>
          <CardContent>
            {isLoadingSchedule ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-[100px]" />
                <Skeleton className="h-4 w-[150px]" />
              </div>
            ) : schedule ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant={schedule.enabled ? 'default' : 'secondary'}>
                    {schedule.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                  {schedule.last_run_status && (
                    <Badge
                      variant={schedule.last_run_status === 'succeeded' ? 'default' : 'destructive'}
                      className={
                        schedule.last_run_status === 'succeeded'
                          ? 'bg-success-bg text-success-fg'
                          : ''
                      }
                    >
                      {schedule.last_run_status}
                    </Badge>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  Next:{' '}
                  <span className="font-mono text-foreground">
                    {schedule.next_run_at
                      ? new Date(schedule.next_run_at).toLocaleString()
                      : '—'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground italic">Failed to load.</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Queue widget — only when something pending or running. */}
      {(queueStats?.pending ?? 0) + (queueStats?.running ?? 0) > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Layers className="h-4 w-4 text-violet" />
              Queue
            </CardTitle>
            <Link to="/health" className="text-xs text-muted-foreground hover:text-violet">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-6 flex-wrap">
              <div>
                <div className="text-2xl font-bold font-mono">{queueStats?.pending ?? 0}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider">
                  Pending
                </div>
              </div>
              <div>
                <div className="text-2xl font-bold font-mono">{queueStats?.running ?? 0}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider">
                  Running
                </div>
              </div>
              {runningItem && (
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-muted-foreground uppercase tracking-wider">
                    Now
                  </div>
                  <div className="text-sm font-mono truncate">
                    {runningItem.inputs.tickers.slice(0, 4).join(', ')}
                    {runningItem.inputs.tickers.length > 4 &&
                      ` +${runningItem.inputs.tickers.length - 4}`}
                  </div>
                </div>
              )}
            </div>
            {(queue?.items.length ?? 0) > 0 && (
              <div className="mt-4 pt-4 border-t border-white/30">
                <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">
                  Pending FIFO
                </div>
                <div className="space-y-1">
                  {queue!.items.map((q, idx) => (
                    <div key={q.id} className="flex items-center justify-between text-xs">
                      <span className="font-mono truncate">
                        #{idx + 1}: {q.inputs.tickers.slice(0, 3).join(', ')}
                        {q.inputs.tickers.length > 3 && '…'}
                      </span>
                      <Badge variant="secondary">{q.source}</Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Row 3 — Recent jobs. */}
      <Card>
        <CardHeader>
          <CardTitle>Recent jobs</CardTitle>
          <CardDescription>The last 5 analysis jobs.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingJobs ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : jobs?.items && jobs.items.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.items.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="text-sm">
                      <Link
                        to={`/health/${job.id}`}
                        className="hover:underline text-foreground"
                      >
                        {job.tickers.length} sym
                        {job.tickers.length === 1 ? '' : 's'} ·{' '}
                        {job.intervals.join('/')} ·{' '}
                        {job.model_ids.length === 1
                          ? job.model_ids[0]
                          : `${job.model_ids.length} models`}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          job.status === 'completed'
                            ? 'default'
                            : job.status === 'failed'
                              ? 'destructive'
                              : 'secondary'
                        }
                        className={
                          job.status === 'completed'
                            ? 'bg-success-bg text-success-fg'
                            : ''
                        }
                      >
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {new Date(job.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground italic">
              No recent jobs found.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
