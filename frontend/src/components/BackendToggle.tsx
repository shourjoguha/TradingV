import { useBackend } from '../hooks/use-backend'
import { useHealth } from '../hooks/use-api'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select'
import { BACKENDS } from '../lib/backend-store'
import type { BackendId } from '../lib/types'

export function BackendToggle() {
  const { backendId, setBackend } = useBackend()
  const { data: isHealthy, isLoading } = useHealth()
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <div
          className={`h-2 w-2 rounded-full ${isLoading ? 'bg-muted' : isHealthy ? 'bg-green-500' : 'bg-red-500'}`}
          title={isLoading ? 'Checking…' : isHealthy ? 'Healthy' : 'Unreachable'}
        />
        <span className="hidden sm:inline-block font-mono text-xs">
          {isLoading ? 'check' : isHealthy ? 'ok' : 'down'}
        </span>
      </div>
      <Select value={backendId} onValueChange={(v) => setBackend(v as BackendId)}>
        <SelectTrigger className="w-[140px] h-8">
          <SelectValue placeholder="Backend" />
        </SelectTrigger>
        <SelectContent>
          {Object.values(BACKENDS).map((b) => (
            <SelectItem key={b.id} value={b.id}>{b.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
