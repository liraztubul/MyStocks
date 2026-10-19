import Big from 'big.js'
import type { HistoryUnavailableReason } from '../api/history'

export type UnavailableMessage = 'notOnDeployment' | 'providerNotConfigured' | 'rateLimited' | 'providerUnavailable'

// Every reason the history endpoint can give has its own message (exhaustive by type).
const MESSAGES: Record<HistoryUnavailableReason, UnavailableMessage> = {
  not_available_on_deployment: 'notOnDeployment',
  provider_not_configured: 'providerNotConfigured',
  rate_limited: 'rateLimited',
  provider_unavailable: 'providerUnavailable',
}

export function unavailableMessage(reason: HistoryUnavailableReason | null): UnavailableMessage {
  return reason ? MESSAGES[reason] : 'providerUnavailable'
}

// "Try again in about N minutes": whole minutes, rounded up, at least 1; null when unknown.
export function retryMinutes(seconds: number | null): number | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds <= 0) return null
  return Math.max(1, Math.ceil(seconds / 60))
}

// Whether a trade's price was moved onto the split-adjusted line (compared exactly, as decimals).
export function isSplitAdjusted(price: string, chartPrice: string): boolean {
  return !Big(price).eq(Big(chartPrice))
}
