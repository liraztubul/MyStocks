import { apiGet, apiPost, retryDelay, retryUnlessDefinite } from './client'

export interface User {
  id: string
  email: string
}

export interface Credentials {
  email: string
  password: string
}

export interface Registration extends Credentials {
  invite_code: string
}

export function register(registration: Registration): Promise<User> {
  return apiPost<User>('/auth/register', registration)
}

export function login(credentials: Credentials): Promise<User> {
  return apiPost<User>('/auth/login', credentials)
}

export function getMe(): Promise<User> {
  return apiGet<User>('/auth/me')
}

// Always 204 and idempotent, so it's safe to repeat: rides out a sleeping backend like a query.
export async function logout(): Promise<void> {
  for (let failures = 0; ; failures++) {
    try {
      return await apiPost<void>('/auth/logout', undefined)
    } catch (error) {
      if (!retryUnlessDefinite(failures, error)) throw error
      await new Promise((resolve) => setTimeout(resolve, retryDelay(failures, error)))
    }
  }
}
