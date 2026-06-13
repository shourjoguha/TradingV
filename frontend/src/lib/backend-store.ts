import type { BackendConfig, BackendId } from './types'

/**
 * Single-backend store. Railway was permanently shut down 2026-05-17 —
 * we keep the `BackendId` plumbing as a single-member union so React-Query
 * cache keys + `apiFetch({backendId})` call sites continue compiling
 * without a sweep. All getters now collapse to the laptop config.
 */
export const BACKENDS: Record<BackendId, BackendConfig> = {
  laptop: {
    id: 'laptop',
    label: 'Laptop',
    baseUrl: import.meta.env.VITE_LAPTOP_URL ?? 'http://localhost:8000',
    apiKey: import.meta.env.VITE_LAPTOP_KEY ?? '',
  },
}

export function isBackendAvailable(_id: BackendId): boolean {
  return true
}

export function availableBackends(): BackendId[] {
  return ['laptop']
}

export function getBackendId(): BackendId {
  return 'laptop'
}

export function setBackendId(_id: BackendId): void {
  // no-op — kept for backward compatibility w/ any caller that
  // still invokes the setter (e.g. legacy BackendHealthBanner).
}

export function getBackendConfig(_id?: BackendId): BackendConfig {
  return BACKENDS.laptop
}
