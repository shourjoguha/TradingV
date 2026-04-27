import React from 'react'
import {
  useSchedule,
  useWatchlist,
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
import { Play, Clock, List, Activity, Layers } from 'lucide-react'
import { Link } from 'react-router-dom'
export function Dashboard() {
  const { data: schedule, isLoading: isLoadingSchedule } = useSchedule()
  const { data: watchlist, isLoading: isLoadingWatchlist } = useWatchlist({
    limit: 1,
  })
  const { data: jobs, isLoading: isLoadingJobs } = useAnalysisJobs({
    limit: 5,
  })
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
          <p className="text-muted-foreground">
            Monitor your prediction models and schedule.
          </p>
        </div>
        <Button
          onClick={() => fireNow()}
          disabled={isFiring || !schedule?.enabled}
          size="lg"
        >
          <Play className="mr-2 h-4 w-4" />
          Run Now
        </Button>
      </div>

      {/* Queue widget — pending + running counts. Hidden when queue is fully empty. */}
      {(queueStats?.pending ?? 0) + (queueStats?.running ?? 0) > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Layers className="h-4 w-4 text-violet" />
              Queue
            </CardTitle>
            <Link to="/analysis" className="text-xs text-muted-foreground hover:text-violet">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-6">
              <div>
                <div className="text-2xl font-bold font-mono">{queueStats?.pending ?? 0}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider">Pending</div>
              </div>
              <div>
                <div className="text-2xl font-bold font-mono">{queueStats?.running ?? 0}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider">Running</div>
              </div>
              {runningItem && (
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-muted-foreground uppercase tracking-wider">Now</div>
                  <div className="text-sm font-mono truncate">
                    {runningItem.inputs.tickers.slice(0, 4).join(', ')}
                    {runningItem.inputs.tickers.length > 4 && ` +${runningItem.inputs.tickers.length - 4}`}
                  </div>
                </div>
              )}
            </div>
            {(queue?.items.length ?? 0) > 0 && (
              <div className="mt-4 pt-4 border-t border-white/30">
                <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">
                  Pending queue (FIFO)
                </div>
                <div className="space-y-1">
                  {queue!.items.map((q, idx) => (
                    <div key={q.id} className="flex items-center justify-between text-xs">
                      <span className="font-mono">
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

      <div className="grid gap-4 md:grid-cols-3">
        {/* Schedule Status Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Schedule Status
            </CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingSchedule ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-[100px]" />
                <Skeleton className="h-4 w-[150px]" />
              </div>
            ) : schedule ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant={schedule.enabled ? 'default' : 'secondary'}>
                    {schedule.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                  {schedule.last_run_status && (
                    <Badge
                      variant={
                        schedule.last_run_status === 'success'
                          ? 'default'
                          : 'destructive'
                      }
                      className={
                        schedule.last_run_status === 'success'
                          ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                          : ''
                      }
                    >
                      {schedule.last_run_status}
                    </Badge>
                  )}
                </div>
                <div className="text-sm text-muted-foreground">
                  Next run:{' '}
                  <span className="font-mono text-foreground">
                    {schedule.next_run_at
                      ? new Date(schedule.next_run_at).toLocaleString()
                      : 'Not scheduled'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                Failed to load schedule
              </div>
            )}
          </CardContent>
        </Card>

        {/* Watchlist Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Watchlist Size
            </CardTitle>
            <List className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingWatchlist ? (
              <Skeleton className="h-8 w-[50px]" />
            ) : (
              <div className="text-2xl font-bold font-mono">
                {watchlist?.total ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Tickers being monitored
            </p>
          </CardContent>
        </Card>

        {/* Jobs Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Recent Activity
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingJobs ? (
              <Skeleton className="h-8 w-[50px]" />
            ) : (
              <div className="text-2xl font-bold font-mono">
                {jobs?.total ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Total analysis jobs run
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Jobs Table */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Analysis Jobs</CardTitle>
          <CardDescription>The last 5 analysis jobs executed.</CardDescription>
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
                  <TableHead>ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Tickers</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.items.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-mono text-xs">
                      <Link
                        to={`/analysis/${job.id}`}
                        className="hover:underline text-primary"
                      >
                        {job.id.substring(0, 8)}...
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
                            ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                            : ''
                        }
                      >
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {new Date(job.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs">
                      {job.tickers.length > 3
                        ? `${job.tickers.slice(0, 3).join(', ')} +${job.tickers.length - 3}`
                        : job.tickers.join(', ')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground">
              No recent jobs found.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
