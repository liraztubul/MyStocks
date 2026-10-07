import { apiDelete, apiGet, apiPost } from './client'
import type { AssetType } from './transactions'

// Decimal fields are strings at full precision; only the display turns them into text.
export interface WatchlistItem {
  symbol: string
  asset_type: AssetType
  coin_id: string | null
  coin_auto_picked: boolean
  added_at: string
  price: string | null
  currency: string | null
  price_as_of: string | null
  stale: boolean
  change_pct: string | null
  change_basis: '24h_rolling' | null
  unavailable_code: string | null
  unavailable_reason: string | null
}

export interface WatchlistAdd {
  symbol: string
  // The coin picked from the candidates; omitted, the server works it out.
  id?: string
}

export function listWatchlist(): Promise<WatchlistItem[]> {
  return apiGet<WatchlistItem[]>('/watchlist')
}

export function addToWatchlist({ symbol, id }: WatchlistAdd): Promise<WatchlistItem> {
  return apiPost<WatchlistItem>('/watchlist', { symbol, type: 'crypto', ...(id && { id }) })
}

export function removeFromWatchlist(symbol: string): Promise<void> {
  return apiDelete(`/watchlist/${encodeURIComponent(symbol)}`)
}
