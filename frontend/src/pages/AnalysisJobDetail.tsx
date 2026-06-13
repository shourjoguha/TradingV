import React from 'react'
import { useParams, Link } from 'react-router-dom'
import { useAnalysisJob } from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Skeleton } from '../components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { ArrowLeft, CheckCircle2, XCircle, Clock, Loader2 } from 'lucide-react'
export function AnalysisJobDetail() {
  const { jobId } = useParams<{
    jobId: string
  }>()
  const { data: job, isLoading } = useAnalysisJob(jobId || '')
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-[200px]" />
        <Card>
          <CardContent className="h-[200px] flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    )
  }
  if (!job) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold mb-2">Job Not Found</h2>
        <Button asChild variant="outline">
          <Link to="/analysis">Back to Jobs</Link>
        </Button>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/analysis">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-3">
            Job Details
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
                  ? 'bg-green-500/10 text-green-500'
                  : ''
              }
            >
              {job.status}
            </Badge>
          </h2>
          <p className="text-muted-foreground font-mono text-sm">{job.id}</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Tasks</CardTitle>
            <CardDescription>
              Individual prediction tasks for this job.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {job.tasks && job.tasks.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticker</TableHead>
                    <TableHead>Interval</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {job.tasks.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className="font-mono font-medium">
                        {task.ticker}
                      </TableCell>
                      <TableCell>{task.interval}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {task.model_id}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {task.status === 'completed' ? (
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                          ) : task.status === 'failed' ? (
                            <XCircle className="h-4 w-4 text-red-500" />
                          ) : task.status === 'running' ? (
                            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                          ) : (
                            <Clock className="h-4 w-4 text-muted-foreground" />
                          )}
                          <span className="text-sm capitalize">
                            {task.status}
                          </span>
                        </div>
                        {task.error && (
                          <div
                            className="text-xs text-red-500 mt-1 max-w-[200px] truncate"
                            title={task.error}
                          >
                            {task.error}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-sm text-muted-foreground text-center py-6">
                No tasks found.
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <div className="text-muted-foreground mb-1">Created At</div>
                <div className="font-mono">
                  {new Date(job.created_at).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">Horizon Bars</div>
                <div className="font-mono">{job.horizon_bars}</div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">
                  Tickers ({job.tickers.length})
                </div>
                <div className="font-mono text-xs break-words">
                  {job.tickers.join(', ')}
                </div>
              </div>
            </CardContent>
          </Card>

          {job.result_json && (
            <Card>
              <CardHeader>
                <CardTitle>Result Data</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="bg-muted p-4 rounded-lg text-xs font-mono overflow-auto max-h-[300px]">
                  {JSON.stringify(job.result_json, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
