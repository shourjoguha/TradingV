import { useBackend } from '../hooks/use-backend'
import { useHealth } from '../hooks/use-api'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select'
import { BACKENDS, availableBackends } from '../lib/backend-store'
import type { BackendId } from '../lib/types'

// Neumorphic backend toggle. The health dot lives in a tiny inset
// well — the same physics as the rest of the UI applied at micro
// scale. Static label form (single backend) uses extruded-sm so it
// reads as a badge, not an interactive control.
export function BackendToggle() {
  const { backendId, setBackend } = useBackend()
  const { data: isHealthy, isLoading } = useHealth()
  const available = availableBackends()
  const dot = (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <div className="rounded-full p-1.5 shadow-inset-sm bg-background">
        <div
          className={`h-2 w-2 rounded-full ${
            isLoading
              ? 'bg-muted-foreground/40'
              : isHealthy
                ? 'bg-success'
                : 'bg-danger'
          }`}
          title={isLoading ? 'Checking…' : isHealthy ? 'Healthy' : 'Unreachable'}
        />
      </div>
      <span className="hidden sm:inline-block font-mono text-xs">
        {isLoading ? 'check' : isHealthy ? 'ok' : 'down'}
      </span>
    </div>
  )
  if (available.length <= 1) {
    return (
      <div className="flex items-center gap-3">
        {dot}
        <span className="text-sm font-medium px-4 py-2 rounded-2xl bg-background shadow-extruded-sm">
          {BACKENDS[backendId].label}
        </span>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-3">
      {dot}
      <Select value={backendId} onValueChange={(v) => setBackend(v as BackendId)}>
        <SelectTrigger className="w-[140px] h-9">
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
