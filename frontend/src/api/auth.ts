import { apiGet, apiPost } from './client'

export interface User {
  id: string
  email: string
}

export interface Credentials {
  email: string
  password: string
}

export function register(credentials: Credentials): Promise<User> {
  return apiPost<User>('/auth/register', credentials)
}

export function login(credentials: Credentials): Promise<User> {
  return apiPost<User>('/auth/login', credentials)
}

export function getMe(): Promise<User> {
  return apiGet<User>('/auth/me')
}
