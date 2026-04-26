import { getBackendConfig } from './backend-store'
import type { BackendId } from './types'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

interface FetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  backendId?: BackendId
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: FetchOptions = {},
): Promise<T> {
  const { body, backendId, ...init } = opts
  const cfg = getBackendConfig(backendId)

  const headers: Record<string, string> = {
    'X-API-Key': cfg.apiKey,
    ...(init.headers as Record<string, string>),
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(`${cfg.baseUrl}${path}`, {
    ...init,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const json = await res.json()
      detail = json.detail ?? JSON.stringify(json)
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function healthCheck(backendId?: BackendId): Promise<boolean> {
  try {
    const cfg = getBackendConfig(backendId)
    const res = await fetch(`${cfg.baseUrl}/health`, {
      signal: AbortSignal.timeout(5000),
    })
    return res.ok
  } catch {
    return false
  }
}
