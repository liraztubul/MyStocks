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

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed: ${response.status}`)
  }
  return (await response.json()) as T
}
