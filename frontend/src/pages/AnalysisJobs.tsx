import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useAnalysisJobs,
  useRunAnalysis,
  useWatchlist,
  useModels,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { Play, FlaskConical } from 'lucide-react'
export function AnalysisJobs() {
  const { data: jobs, isLoading } = useAnalysisJobs({
    limit: 50,
  })
  const { data: watchlist } = useWatchlist({
    limit: 100,
  })
  const { data: models } = useModels()
  const { mutate: runAnalysis, isPending: isRunning } = useRunAnalysis()
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
      {
        tickers,
        intervals,
        model_ids,
        horizon_bars: runForm.horizon_bars,
      },
      {
        onSuccess: () => setIsRunOpen(false),
      },
    )
  }
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Analysis Jobs
          </h2>
          <p className="text-muted-foreground">
            Run and monitor batch prediction tasks.
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
                    setRunForm({
                      ...runForm,
                      tickers: e.target.value,
                    })
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
                          tickers: watchlist.items
                            .map((i) => i.symbol)
                            .join(', '),
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
                  placeholder="1d, 1h"
                  value={runForm.intervals}
                  onChange={(e) =>
                    setRunForm({
                      ...runForm,
                      intervals: e.target.value,
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Models (comma separated)</Label>
                <Input
                  placeholder="model_v1"
                  value={runForm.model_ids}
                  onChange={(e) =>
                    setRunForm({
                      ...runForm,
                      model_ids: e.target.value,
                    })
                  }
                />
                <div className="flex gap-2 mt-1">
                  {models?.map((m) => (
                    <Badge
                      key={m.id}
                      variant="outline"
                      className="cursor-pointer hover:bg-secondary"
                      onClick={() => {
                        const current = runForm.model_ids
                          ? runForm.model_ids.split(',').map((s) => s.trim())
                          : []
                        if (!current.includes(m.id)) {
                          setRunForm({
                            ...runForm,
                            model_ids: [...current, m.id].join(', '),
                          })
                        }
                      }}
                    >
                      {m.id}
                    </Badge>
                  ))}
                </div>
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

      <Card>
        <CardHeader>
          <CardTitle>Job History</CardTitle>
          <CardDescription>Recent batch analysis executions.</CardDescription>
        </CardHeader>
        <CardContent>
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
                  <TableHead>Job ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Config</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.items.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-mono text-sm font-medium">
                      {job.id.substring(0, 8)}...
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          job.status === 'completed'
                            ? 'default'
                            : job.status === 'failed'
                              ? 'destructive'
                              : job.status === 'running'
                                ? 'secondary'
                                : 'outline'
                        }
                        className={
                          job.status === 'completed'
                            ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                            : job.status === 'running'
                              ? 'bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 animate-pulse'
                              : ''
                        }
                      >
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {new Date(job.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                      {job.tickers.length} tickers, {job.intervals.join(',')},{' '}
                      {job.model_ids.join(',')}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" asChild>
                        <Link to={`/analysis/${job.id}`}>View Details</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-12 text-sm text-muted-foreground border border-dashed rounded-lg flex flex-col items-center">
              <FlaskConical className="h-8 w-8 mb-2 text-muted-foreground/50" />
              No analysis jobs found. Run a new analysis to get started.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
