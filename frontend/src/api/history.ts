import { apiGet } from './client'
import type { AssetType, Side } from './transactions'

export type HistoryRange = '1M' | '3M' | '6M' | 'YTD' | '1Y' | 'ALL'
export const HISTORY_RANGES: HistoryRange[] = ['1M', '3M', '6M', 'YTD', '1Y', 'ALL']

// Why there is no chart (see the backend's HistoryRead.unavailable_reason).
export type HistoryUnavailableReason =
  | 'not_available_on_deployment'
  | 'provider_not_configured'
  | 'rate_limited'
  | 'provider_unavailable'

export type UndrawnReason = 'before_range' | 'after_range' | 'no_chart' | 'different_coin'

// Decimal fields are strings at full precision (closes keep 18 places).
export interface HistoryMarker {
  transaction_id: string
  side: Side
  date: string
  trade_date: string
  snapped: boolean
  quantity: string
  // What was actually paid or received.
  price: string
  // Where the marker sits: for stocks, the price divided by the splits after the trade (equals
  // price when nothing was adjusted).
  chart_price: string
}

export interface UndrawnTrade {
  transaction_id: string
  side: Side
  trade_date: string
  quantity: string
  price: string
  reason: UndrawnReason
}

export interface CoinCandidate {
  id: string
  symbol: string
  name: string
  rank: number | null
}

export interface AssetHistory {
  symbol: string
  asset_type: AssetType
  available: boolean
  unavailable_reason: HistoryUnavailableReason | null
  // Stocks: closes are split-adjusted, dividends not included. Null for crypto (raw closes).
  adjustment: 'split_adjusted' | null
  // With rate_limited: seconds until stock history may be asked for again (null if unknown).
  retry_after: number | null
  ambiguous: boolean
  candidates: CoinCandidate[]
  provider: string | null
  coin_id: string | null
  coin_name: string | null
  coin_auto_picked: boolean
  range: HistoryRange
  range_start: string | null
  range_end: string | null
  range_note: string | null
  bars: { date: string; close: string }[]
  splits: { date: string; ratio: string }[]
  markers: HistoryMarker[]
  undrawn_trades: UndrawnTrade[]
  as_of: string | null
  is_stale: boolean
  stale_reason: string | null
}

export interface HistoryParams {
  symbol: string
  range: HistoryRange
  type: AssetType | null
  id: string | null
}

export function getHistory({ symbol, range, type, id }: HistoryParams): Promise<AssetHistory> {
  const query = new URLSearchParams({ range })
  if (type) query.set('type', type)
  if (id) query.set('id', id)
  return apiGet<AssetHistory>(`/assets/${encodeURIComponent(symbol)}/history?${query}`)
}
