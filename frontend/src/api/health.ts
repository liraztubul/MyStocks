import { apiGet } from './client'

export interface HealthResponse {
  status: string
}

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}
