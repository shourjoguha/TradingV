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

export function getBackendId(): BackendId {
  if (typeof window === 'undefined') return 'laptop'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'laptop' || stored === 'railway') return stored
  return 'laptop'
}

export function setBackendId(id: BackendId): void {
  localStorage.setItem(STORAGE_KEY, id)
}

export function getBackendConfig(id?: BackendId): BackendConfig {
  return BACKENDS[id ?? getBackendId()]
}
