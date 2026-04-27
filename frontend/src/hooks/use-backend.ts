import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { getBackendId, isBackendAvailable, setBackendId } from '../lib/backend-store'
import type { BackendId } from '../lib/types'

const listeners = new Set<() => void>()
function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function useBackend() {
  const backendId = useSyncExternalStore(subscribe, getBackendId, getBackendId)
  const setBackend = useCallback((id: BackendId) => {
    setBackendId(id)
    listeners.forEach((l) => l())
  }, [])
  useEffect(() => {
    if (!isBackendAvailable(backendId)) {
      setBackend(getBackendId())
    }
  }, [backendId, setBackend])
  return { backendId, setBackend } as const
}
