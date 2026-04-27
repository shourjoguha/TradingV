import type { BackendConfig, BackendId } from './types'

const STORAGE_KEY = 'kronos_backend'

export const BACKENDS: Record<BackendId, BackendConfig> = {
  laptop: {
    id: 'laptop',
    label: 'Laptop',
    baseUrl: import.meta.env.VITE_LAPTOP_URL ?? 'http://localhost:8000',
    apiKey: import.meta.env.VITE_LAPTOP_KEY ?? '',
  },
  railway: {
    id: 'railway',
    label: 'Railway',
    baseUrl:
      import.meta.env.VITE_RAILWAY_URL ??
      'https://tradingv-production.up.railway.app',
    apiKey: import.meta.env.VITE_RAILWAY_KEY ?? '',
  },
}

const DEFAULT_BACKEND_ENV = import.meta.env.VITE_DEFAULT_BACKEND
const DEFAULT_BACKEND: BackendId =
  DEFAULT_BACKEND_ENV === 'railway' || DEFAULT_BACKEND_ENV === 'laptop'
    ? DEFAULT_BACKEND_ENV
    : 'laptop'

export function isBackendAvailable(id: BackendId): boolean {
  if (id === 'laptop' && import.meta.env.DEV) return true
  return BACKENDS[id].baseUrl !== ''
}

export function availableBackends(): BackendId[] {
  return (Object.keys(BACKENDS) as BackendId[]).filter(isBackendAvailable)
}

function resolveDefault(): BackendId {
  if (isBackendAvailable(DEFAULT_BACKEND)) return DEFAULT_BACKEND
  const first = availableBackends()[0]
  return first ?? 'laptop'
}

export function getBackendId(): BackendId {
  if (typeof window === 'undefined') return resolveDefault()
  const stored = localStorage.getItem(STORAGE_KEY)
  if ((stored === 'laptop' || stored === 'railway') && isBackendAvailable(stored)) {
    return stored
  }
  return resolveDefault()
}

export function setBackendId(id: BackendId): void {
  localStorage.setItem(STORAGE_KEY, id)
}

export function getBackendConfig(id?: BackendId): BackendConfig {
  return BACKENDS[id ?? getBackendId()]
}
