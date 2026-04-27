import React, { useEffect, useState } from 'react'
import {
  useSchedule,
  useUpdateSchedule,
  useModels,
  useFireNow,
} from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Switch } from '../components/ui/switch'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { Play, Save } from 'lucide-react'
import type { ScheduleUpdate } from '../lib/types'
export function Schedule() {
  const { data: schedule, isLoading: isLoadingSchedule } = useSchedule()
  const { data: models, isLoading: isLoadingModels } = useModels()
  const { mutate: updateSchedule, isPending: isUpdating } = useUpdateSchedule()
  const { mutate: fireNow, isPending: isFiring } = useFireNow()
  const [formData, setFormData] = useState<ScheduleUpdate>({})
  // Initialize form data when schedule loads
  useEffect(() => {
    if (schedule) {
      setFormData({
        enabled: schedule.enabled,
        tz_name: schedule.tz_name,
        run_at_local: schedule.run_at_local,
        intervals: schedule.intervals,
        horizon_bars: schedule.horizon_bars,
        model_ids: schedule.model_ids,
        retry_minutes: schedule.retry_minutes,
        collect_actuals: schedule.collect_actuals,
        skip_weekends: schedule.skip_weekends,
      })
    }
  }, [schedule])
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateSchedule(formData)
  }
  const handleIntervalToggle = (interval: string) => {
    const current = formData.intervals || []
    if (current.includes(interval)) {
      setFormData({
        ...formData,
        intervals: current.filter((i) => i !== interval),
      })
    } else {
      setFormData({
        ...formData,
        intervals: [...current, interval],
      })
    }
  }
  const handleModelToggle = (modelId: string) => {
    const current = formData.model_ids || []
    if (current.includes(modelId)) {
      setFormData({
        ...formData,
        model_ids: current.filter((m) => m !== modelId),
      })
    } else {
      setFormData({
        ...formData,
        model_ids: [...current, modelId],
      })
    }
  }
  if (isLoadingSchedule || isLoadingModels) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-[200px]" />
        <Card>
          <CardContent className="p-6 space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Schedule
          </h2>
          <p className="text-muted-foreground">
            Configure automated prediction runs.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => fireNow()}
            disabled={isFiring || !schedule?.enabled}
          >
            <Play className="mr-2 h-4 w-4" />
            Fire Now
          </Button>
          <Button onClick={handleSubmit} disabled={isUpdating}>
            <Save className="mr-2 h-4 w-4" />
            Save Changes
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Timing & Execution</CardTitle>
              <CardDescription>
                When should the prediction pipeline run?
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between p-4 rounded-2xl shadow-inset-sm">
                <div className="space-y-0.5">
                  <Label className="text-base">Enable Schedule</Label>
                  <p className="text-sm text-muted-foreground">
                    Turn automated runs on or off.
                  </p>
                </div>
                <Switch
                  checked={formData.enabled || false}
                  onCheckedChange={(c) =>
                    setFormData({
                      ...formData,
                      enabled: c,
                    })
                  }
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Timezone (IANA)</Label>
                  <Input
                    value={formData.tz_name || ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        tz_name: e.target.value,
                      })
                    }
                    placeholder="America/New_York"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Run At (Local Time)</Label>
                  <Input
                    type="time"
                    value={formData.run_at_local || ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        run_at_local: e.target.value,
                      })
                    }
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-center justify-between p-4 rounded-2xl shadow-inset-sm">
                  <div className="space-y-0.5">
                    <Label>Skip Weekends</Label>
                    <p className="text-xs text-muted-foreground">
                      Don't run on Sat/Sun
                    </p>
                  </div>
                  <Switch
                    checked={formData.skip_weekends || false}
                    onCheckedChange={(c) =>
                      setFormData({
                        ...formData,
                        skip_weekends: c,
                      })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Retry Minutes</Label>
                  <Input
                    type="number"
                    value={formData.retry_minutes || 0}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        retry_minutes: parseInt(e.target.value),
                      })
                    }
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Pipeline Configuration</CardTitle>
              <CardDescription>
                What should the pipeline predict?
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3">
                <Label>Intervals</Label>
                <div className="flex flex-wrap gap-2">
                  {['1d', '1h', '15m', '5m', '1m'].map((interval) => (
                    <Badge
                      key={interval}
                      variant={
                        formData.intervals?.includes(interval)
                          ? 'default'
                          : 'outline'
                      }
                      className="cursor-pointer px-3 py-1 text-sm"
                      onClick={() => handleIntervalToggle(interval)}
                    >
                      {interval}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                <Label>Models</Label>
                <div className="flex flex-wrap gap-2">
                  {models?.map((model) => (
                    <Badge
                      key={model.id}
                      variant={
                        formData.model_ids?.includes(model.id)
                          ? 'default'
                          : 'outline'
                      }
                      className="cursor-pointer px-3 py-1 text-sm"
                      onClick={() => handleModelToggle(model.id)}
                    >
                      {model.id}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Horizon Bars</Label>
                  <Input
                    type="number"
                    value={formData.horizon_bars || 1}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        horizon_bars: parseInt(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="flex items-center justify-between p-4 rounded-2xl shadow-inset-sm mt-6">
                  <div className="space-y-0.5">
                    <Label>Collect Actuals</Label>
                    <p className="text-xs text-muted-foreground">
                      Fetch latest OHLCV
                    </p>
                  </div>
                  <Switch
                    checked={formData.collect_actuals || false}
                    onCheckedChange={(c) =>
                      setFormData({
                        ...formData,
                        collect_actuals: c,
                      })
                    }
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="text-sm text-muted-foreground mb-1">
                  Next Run
                </div>
                <div className="font-mono bg-muted p-2 rounded text-sm">
                  {schedule?.next_run_at
                    ? new Date(schedule.next_run_at).toLocaleString()
                    : 'Not scheduled'}
                </div>
              </div>
              <div>
                <div className="text-sm text-muted-foreground mb-1">
                  Last Run
                </div>
                <div className="font-mono bg-muted p-2 rounded text-sm">
                  {schedule?.last_run_at
                    ? new Date(schedule.last_run_at).toLocaleString()
                    : 'Never'}
                </div>
              </div>
              <div>
                <div className="text-sm text-muted-foreground mb-1">
                  Last Status
                </div>
                <Badge
                  variant={
                    schedule?.last_run_status === 'success'
                      ? 'default'
                      : schedule?.last_run_status === 'failed'
                        ? 'destructive'
                        : 'secondary'
                  }
                >
                  {schedule?.last_run_status || 'Unknown'}
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
