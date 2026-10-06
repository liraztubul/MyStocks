export class ApiError extends Error {
  readonly status: number
  // Seconds to wait, from a 429's Retry-After header; null when absent or unparseable.
  readonly retryAfter: number | null
  // The backend's machine-readable reason, when it sends one (e.g. not_available_on_deployment).
  readonly code: string | null

  constructor(status: number, message: string, retryAfter: number | null = null, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
    this.code = code
  }
}

// Retry-After is either delta-seconds or an HTTP date.
function parseRetryAfter(header: string | null): number | null {
  if (!header) return null
  if (/^\d+$/.test(header.trim())) return Number(header.trim())
  const at = Date.parse(header)
  return Number.isNaN(at) ? null : Math.max(0, Math.ceil((at - Date.now()) / 1000))
}

// Relative base: Vite's dev proxy and nginx in Docker both forward /api to the backend,
// so the browser always talks same-origin and we avoid CORS entirely.
const API_BASE = '/api'

// The free-tier backend sleeps when idle and takes about a minute to wake. While it does, the
// proxy can answer 502/503/504 or the connection can drop; those mean "try again", not "failed".
const WAKING_STATUSES = new Set([502, 503, 504])
const WAKE_RETRY_DELAY_MS = 5_000
const WAKE_MAX_RETRIES = 24 // ~2 minutes at 5 s
const OTHER_MAX_RETRIES = 3

export function isServerWaking(error: unknown): boolean {
  if (error instanceof ApiError) return WAKING_STATUSES.has(error.status)
  // fetch rejects with a TypeError on network failure (no HTTP response at all).
  return error instanceof TypeError
}

// Shared TanStack Query retry policy: wait out a cold start, give up quickly on anything else.
export function retryUnlessDefinite(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false
  return failureCount < (isServerWaking(error) ? WAKE_MAX_RETRIES : OTHER_MAX_RETRIES)
}

export function retryDelay(attempt: number, error: unknown): number {
  return isServerWaking(error) ? WAKE_RETRY_DELAY_MS : Math.min(1000 * 2 ** attempt, 30_000)
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(body !== undefined && { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const { message, code } = await errorBody(response)
    throw new ApiError(response.status, message, parseRetryAfter(response.headers.get('Retry-After')), code)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

// FastAPI returns {detail: string} for HTTPExceptions and {detail: [{msg}, ...]} for validation;
// market-data errors add a {code}.
async function errorBody(response: Response): Promise<{ message: string; code: string | null }> {
  const fallback = `Request failed (${response.status})`
  try {
    const { detail, code } = (await response.json()) as { detail?: unknown; code?: unknown }
    const reason = typeof code === 'string' ? code : null
    if (typeof detail === 'string') return { message: detail, code: reason }
    if (Array.isArray(detail)) {
      return { message: detail.map((d: { msg?: string }) => d.msg ?? 'Invalid input').join('; '), code: reason }
    }
    return { message: fallback, code: reason }
  } catch {
    // Non-JSON error body; fall through to the generic message.
  }
  return { message: fallback, code: null }
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>('GET', path)
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>('POST', path, body)
}

export function apiDelete(path: string): Promise<void> {
  return request<void>('DELETE', path)
}
