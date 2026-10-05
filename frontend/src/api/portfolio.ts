import { apiGet } from './client'
import type { AssetType } from './transactions'

// Decimal fields arrive as strings at full API precision; round only when displaying.
export interface Holding {
  symbol: string
  asset_type: AssetType
  quantity: string
  average_cost: string
  cost_basis: string
  current_price: string | null
  market_value: string | null
  unrealized_pl: string | null
  unrealized_pl_pct: string | null
  allocation_pct: string | null
  price_as_of: string | null
  price_is_stale: boolean
  price_unavailable_reason: string | null
}

export function getHoldings(): Promise<Holding[]> {
  return apiGet<Holding[]>('/portfolio/holdings')
}
