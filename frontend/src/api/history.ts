import { apiGet } from './client'
import type { AssetType, Side } from './transactions'

export type HistoryRange = '1M' | '3M' | '6M' | 'YTD' | '1Y' | 'ALL'
export const HISTORY_RANGES: HistoryRange[] = ['1M', '3M', '6M', 'YTD', '1Y', 'ALL']

export type UndrawnReason = 'before_range' | 'after_range' | 'no_chart' | 'different_coin'

// Decimal fields are strings at full precision (closes keep 18 places).
export interface HistoryMarker {
  transaction_id: string
  side: Side
  date: string
  trade_date: string
  snapped: boolean
  quantity: string
  price: string
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
  unavailable_reason: 'not_available_on_deployment' | 'provider_not_configured' | null
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
