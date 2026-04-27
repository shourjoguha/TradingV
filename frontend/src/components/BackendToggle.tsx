import { useBackend } from '../hooks/use-backend'
import { useHealth } from '../hooks/use-api'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select'
import { BACKENDS, availableBackends } from '../lib/backend-store'
import type { BackendId } from '../lib/types'

export function BackendToggle() {
  const { backendId, setBackend } = useBackend()
  const { data: isHealthy, isLoading } = useHealth()
  const available = availableBackends()
  const dot = (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <div
        className={`h-2 w-2 rounded-full ${isLoading ? 'bg-muted' : isHealthy ? 'bg-green-500' : 'bg-red-500'}`}
        title={isLoading ? 'Checking…' : isHealthy ? 'Healthy' : 'Unreachable'}
      />
      <span className="hidden sm:inline-block font-mono text-xs">
        {isLoading ? 'check' : isHealthy ? 'ok' : 'down'}
      </span>
    </div>
  )
  if (available.length <= 1) {
    return (
      <div className="flex items-center gap-3">
        {dot}
        <span className="text-sm font-medium px-3 py-1 rounded border bg-muted/40">
          {BACKENDS[backendId].label}
        </span>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-3">
      {dot}
      <Select value={backendId} onValueChange={(v) => setBackend(v as BackendId)}>
        <SelectTrigger className="w-[140px] h-8">
          <SelectValue placeholder="Backend" />
        </SelectTrigger>
        <SelectContent>
          {available.map((id) => (
            <SelectItem key={id} value={id}>{BACKENDS[id].label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
