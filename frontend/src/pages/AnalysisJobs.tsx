import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useAnalysisJobs,
  useAnalysisJob,
  useRunAnalysis,
  useWatchlist,
  useModels,
  useQueue,
  useCancelQueueItem,
} from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '../components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Skeleton } from '../components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import {
  Play,
  FlaskConical,
  X,
  Layers,
  ChevronRight,
  ChevronDown,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  AlertTriangle,
} from 'lucide-react'
import type { AnalysisJob, AnalysisTask } from '../lib/types'
import { EmptyState } from '../components/common'

// ---------------------------------------------------------------------------
// Smart-time helpers — collapse a timestamp into "Today HH:mm", "Yesterday
// HH:mm", "Mon HH:mm" (this week), or "MMM D HH:mm" (older). Operator scans
// these by eye instead of decoding ISO strings.
// ---------------------------------------------------------------------------
function smartWhen(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const startOfDay = (x: Date) =>
    new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86400000)
  if (days === 0) return `Today ${time}`
  if (days === 1) return `Yesterday ${time}`
  if (days > 1 && days < 7)
    return `${d.toLocaleDateString([], { weekday: 'short' })} ${time}`
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`
}

// "1m 12s" / "32s" / "—" if no timestamps yet.
function fmtDuration(start?: string | null, end?: string | null): string {
  if (!start) return '—'
  const a = new Date(start).getTime()
  const b = end ? new Date(end).getTime() : Date.now()
  const sec = Math.max(0, Math.round((b - a) / 1000))
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s ? `${m}m ${s}s` : `${m}m`
}

// Bucket task statuses into the four columns we display in the outcome bar.
// Backend strings have varied historically — accept both 'done'/'completed'
// and 'error'/'failed' so the bar renders correctly across versions.
type Bucket = 'done' | 'ineligible' | 'error' | 'running'
function bucketize(tasks: AnalysisTask[]): Record<Bucket, number> {
  const out: Record<Bucket, number> = { done: 0, ineligible: 0, error: 0, running: 0 }
  for (const t of tasks) {
    const s = (t.status || '').toLowerCase()
    if (s === 'done' || s === 'completed') out.done += 1
    else if (s === 'ineligible') out.ineligible += 1
    else if (s === 'error' || s === 'failed') out.error += 1
    else out.running += 1
  }
  return out
}

// Friendly job summary: "schedule · 40 syms · 1d · kronos_base". Falls back
// gracefully when fields are missing.
function jobSummary(job: AnalysisJob): string {
  const parts: string[] = []
  parts.push(`${job.tickers.length} sym${job.tickers.length === 1 ? '' : 's'}`)
  if (job.intervals.length > 0) parts.push(job.intervals.join('/'))
  if (job.model_ids.length === 1) parts.push(job.model_ids[0])
  else if (job.model_ids.length > 1) parts.push(`${job.model_ids.length} models`)
  return parts.join(' · ')
}

// ---------------------------------------------------------------------------
// Outcome bar — stacked horizontal bar for a job's per-task statuses.
// ---------------------------------------------------------------------------
function OutcomeBar({
  buckets,
  total,
}: {
  buckets: Record<Bucket, number>
  total: number
}) {
  if (total === 0) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  const segments: Array<{ bucket: Bucket; count: number; cls: string; label: string }> = (
    [
      { bucket: 'done', count: buckets.done, cls: 'bg-success', label: 'done' },
      { bucket: 'running', count: buckets.running, cls: 'bg-blue-400', label: 'running' },
      { bucket: 'ineligible', count: buckets.ineligible, cls: 'bg-warning', label: 'ineligible' },
      { bucket: 'error', count: buckets.error, cls: 'bg-danger', label: 'error' },
    ] as const
  ).filter((s) => s.count > 0).map((s) => ({ ...s }))
  return (
    <div className="space-y-1 min-w-[140px]">
      <div
        className="h-2 w-full rounded-full overflow-hidden flex shadow-inset-sm bg-background"
        title={segments.map((s) => `${s.label}: ${s.count}`).join(' · ')}
      >
        {segments.map((s) => (
          <div
            key={s.bucket}
            className={s.cls}
            style={{ width: `${(s.count / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs font-mono text-muted-foreground">
        {segments.map((s) => (
          <span key={s.bucket}>
            {s.label}: <span className="text-foreground font-medium">{s.count}</span>
          </span>
        ))}
        <span>· total: {total}</span>
      </div>
    </div>
  )
}

function statusIcon(status: string) {
  const s = status.toLowerCase()
  if (s === 'done' || s === 'completed')
    return <CheckCircle2 className="h-3.5 w-3.5 text-success" />
  if (s === 'failed' || s === 'error')
    return <XCircle className="h-3.5 w-3.5 text-danger" />
  if (s === 'ineligible')
    return <AlertTriangle className="h-3.5 w-3.5 text-warning" />
  if (s === 'running')
    return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin" />
  return <Clock className="h-3.5 w-3.5 text-muted-foreground" />
}

// ---------------------------------------------------------------------------
// JobRow — one row in the history table. Owns its expand state + lazy task
// fetch. Detail data is cached per-jobId by React Query so re-expanding is
// instant.
// ---------------------------------------------------------------------------
function JobRow({ job }: { job: AnalysisJob }) {
  const [expanded, setExpanded] = useState(false)
  const detailQuery = useAnalysisJob(expanded ? job.id : '')
  const detail = expanded ? detailQuery.data : undefined

  const taskCount = detail?.tasks?.length ?? job.task_count ?? 0
  // Prefer fresh task data when expanded; otherwise use the per-bucket
  // counts the list endpoint now returns (added in the IA-reorg follow-up
  // so collapsed rows render the OutcomeBar without a per-row fetch).
  const buckets: Record<Bucket, number> = useMemo(() => {
    if (detail?.tasks) return bucketize(detail.tasks)
    return {
      done: job.done ?? 0,
      ineligible: job.ineligible ?? 0,
      error: job.error ?? 0,
      running: (job.running ?? 0) + (job.pending ?? 0),
    }
  }, [detail, job])
  const hasListBuckets =
    (job.done ?? 0) +
      (job.ineligible ?? 0) +
      (job.error ?? 0) +
      (job.running ?? 0) +
      (job.pending ?? 0) >
    0

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <TableCell className="w-8 align-top pt-3">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell className="align-top">
          <div className="flex items-center gap-2">
            {statusIcon(job.status)}
            <div>
              <div className="font-medium text-sm leading-tight">{jobSummary(job)}</div>
              <div
                className="text-xs font-mono text-muted-foreground truncate max-w-[260px]"
                title={job.tickers.join(', ')}
              >
                {job.tickers.slice(0, 6).join(' ')}
                {job.tickers.length > 6 ? ` +${job.tickers.length - 6}` : ''}
              </div>
            </div>
          </div>
        </TableCell>
        <TableCell className="align-top">
          {(expanded && detail?.tasks) || hasListBuckets ? (
            <OutcomeBar buckets={buckets} total={taskCount} />
          ) : (
            <Badge
              variant="outline"
              className={
                job.status === 'completed' || job.status === 'done'
                  ? 'bg-success-bg text-success-fg'
                  : job.status === 'failed' || job.status === 'error'
                    ? 'bg-danger-bg text-danger-fg'
                    : job.status === 'running'
                      ? 'bg-blue-100 text-blue-700 animate-pulse'
                      : ''
              }
            >
              {job.status}{taskCount ? ` · ${taskCount}` : ''}
            </Badge>
          )}
        </TableCell>
        <TableCell
          className="align-top text-xs font-mono text-muted-foreground"
          title={new Date(job.created_at).toISOString()}
        >
          {smartWhen(job.created_at)}
        </TableCell>
        <TableCell className="align-top text-xs font-mono text-muted-foreground">
          {fmtDuration(job.created_at, job.finished_at ?? null)}
        </TableCell>
        <TableCell className="align-top text-right">
          <Button
            variant="ghost"
            size="icon"
            asChild
            onClick={(e) => e.stopPropagation()}
            title="Open detail page"
          >
            <Link to={`/analysis/${job.id}`}>
              <ExternalLink className="h-4 w-4" />
            </Link>
          </Button>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow className="bg-muted/20">
          <TableCell colSpan={6} className="py-3">
            {detailQuery.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : !detail?.tasks || detail.tasks.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                No tasks found for this job.
              </div>
            ) : (
              <div className="rounded-xl bg-background shadow-inset-sm overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs uppercase">Ticker</TableHead>
                      <TableHead className="text-xs uppercase">Interval</TableHead>
                      <TableHead className="text-xs uppercase">Model</TableHead>
                      <TableHead className="text-xs uppercase">Status</TableHead>
                      <TableHead className="text-xs uppercase">Detail</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.tasks.map((task) => {
                      const reason = (task as AnalysisTask & {
                        ineligible_reason?: string
                        ineligible_message?: string
                      })
                      return (
                        <TableRow key={task.id}>
                          <TableCell className="font-mono font-medium text-sm">
                            {task.ticker}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {task.interval}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {task.model_id}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1.5">
                              {statusIcon(task.status)}
                              <span className="text-xs capitalize">{task.status}</span>
                            </div>
                          </TableCell>
                          <TableCell
                            className="text-[11px] text-muted-foreground max-w-[280px] truncate"
                            title={reason.ineligible_message || task.error || ''}
                          >
                            {reason.ineligible_reason
                              ? `${reason.ineligible_reason}${
                                  reason.ineligible_message
                                    ? ` — ${reason.ineligible_message}`
                                    : ''
                                }`
                              : task.error || '—'}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export function AnalysisJobs() {
  const { data: jobs, isLoading } = useAnalysisJobs({ limit: 50 })
  const { data: watchlist } = useWatchlist({ limit: 100 })
  const { data: models } = useModels()
  const { mutate: runAnalysis, isPending: isRunning } = useRunAnalysis()
  const { data: pendingQueue } = useQueue({ status: 'pending', limit: 20 })
  const { data: runningQueue } = useQueue({ status: 'running', limit: 5 })
  const cancel = useCancelQueueItem()
  const queueItems = [
    ...(runningQueue?.items ?? []),
    ...(pendingQueue?.items ?? []),
  ]
  const [isRunOpen, setIsRunOpen] = useState(false)
  const [runForm, setRunForm] = useState({
    tickers: '',
    intervals: '1d',
    model_ids: '',
    horizon_bars: 5,
  })
  const handleRun = () => {
    const tickers = runForm.tickers
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
    const intervals = runForm.intervals
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    const model_ids = runForm.model_ids
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    if (!tickers.length || !intervals.length || !model_ids.length) {
      alert('Please fill all required fields')
      return
    }
    runAnalysis(
      { tickers, intervals, model_ids, horizon_bars: runForm.horizon_bars },
      { onSuccess: () => setIsRunOpen(false) },
    )
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Analysis Jobs
          </h2>
          <p className="text-muted-foreground">
            Run and monitor batch prediction tasks. Click any row to expand its task breakdown.
          </p>
        </div>
        <Dialog open={isRunOpen} onOpenChange={setIsRunOpen}>
          <DialogTrigger asChild>
            <Button>
              <Play className="mr-2 h-4 w-4" /> New Analysis
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Run Analysis Job</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>Tickers (comma separated)</Label>
                <Input
                  placeholder="AAPL, MSFT"
                  value={runForm.tickers}
                  onChange={(e) =>
                    setRunForm({ ...runForm, tickers: e.target.value })
                  }
                  className="font-mono uppercase"
                />
                <div className="flex gap-2 mt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-xs"
                    onClick={() => {
                      if (watchlist?.items) {
                        setRunForm({
                          ...runForm,
                          tickers: watchlist.items.map((i) => i.symbol).join(', '),
                        })
                      }
                    }}
                  >
                    Add All Watchlist
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Intervals (comma separated)</Label>
                <Input
                  placeholder="1d"
                  value={runForm.intervals}
                  onChange={(e) =>
                    setRunForm({ ...runForm, intervals: e.target.value })
                  }
                  className="font-mono"
                />
              </div>
              <div className="space-y-2">
                <Label>Models (comma separated)</Label>
                <Input
                  placeholder="kronos_base"
                  value={runForm.model_ids}
                  onChange={(e) =>
                    setRunForm({ ...runForm, model_ids: e.target.value })
                  }
                  className="font-mono"
                />
                {models && models.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {models.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => {
                          const cur = runForm.model_ids
                            .split(',')
                            .map((s) => s.trim())
                            .filter(Boolean)
                          if (!cur.includes(m.id)) {
                            setRunForm({
                              ...runForm,
                              model_ids: [...cur, m.id].join(', '),
                            })
                          }
                        }}
                        className="text-xs font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                      >
                        +{m.id}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <Label>Horizon Bars</Label>
                <Input
                  type="number"
                  value={runForm.horizon_bars}
                  onChange={(e) =>
                    setRunForm({
                      ...runForm,
                      horizon_bars: parseInt(e.target.value),
                    })
                  }
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsRunOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleRun} disabled={isRunning}>
                Start Job
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {queueItems.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              Queue
            </CardTitle>
            <CardDescription>
              Worker drains FIFO. Cancel pending items before they start.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {queueItems.map((q) => (
                <div
                  key={q.id}
                  className="flex items-center justify-between p-3 rounded-2xl shadow-inset-sm"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Badge variant={q.status === 'running' ? 'success' : 'secondary'}>
                      {q.status}
                    </Badge>
                    <Badge variant="outline">{q.source}</Badge>
                    <div className="text-sm font-mono truncate">
                      {q.inputs.tickers.slice(0, 5).join(', ')}
                      {q.inputs.tickers.length > 5 &&
                        ` +${q.inputs.tickers.length - 5}`}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-mono hidden sm:inline">
                      {new Date(q.enqueued_at).toLocaleTimeString()}
                    </span>
                    {q.status === 'pending' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => cancel.mutate(q.id)}
                        disabled={cancel.isPending}
                        title="Cancel"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Job History</CardTitle>
          <CardDescription>
            Recent batch analysis executions. Click a row to inspect its tasks inline; the icon on
            the right opens the full detail page.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : jobs?.items && jobs.items.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Run</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>When</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead className="text-right">Open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.items.map((job) => (
                  <JobRow key={job.id} job={job} />
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState
              icon={FlaskConical}
              title="No analysis jobs yet"
              description="Run a new analysis from the New Analysis button above to get started."
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
