export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Relative base: Vite's dev proxy and nginx in Docker both forward /api to the backend,
// so the browser always talks same-origin and we avoid CORS entirely.
const API_BASE = '/api'

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
    throw new ApiError(response.status, await errorMessage(response))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

// FastAPI returns {detail: string} for HTTPExceptions and {detail: [{msg}, ...]} for validation.
async function errorMessage(response: Response): Promise<string> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown }
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((d: { msg?: string }) => d.msg ?? 'Invalid input').join('; ')
    }
  } catch {
    // Non-JSON error body; fall through to the generic message.
  }
  return `Request failed (${response.status})`
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
