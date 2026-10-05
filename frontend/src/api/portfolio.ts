import { apiGet } from './client'
import type { AssetType } from './transactions'

// Stocks: since the previous session's close. Crypto: CoinGecko's rolling 24h window.
export type DayChangeBasis = 'since_previous_close' | 'rolling_24h'

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
  day_change: string | null
  day_change_pct: string | null
  day_change_basis: DayChangeBasis | null
  day_change_reference_price: string | null
  day_change_reference_at: string | null
}

export interface PortfolioSummary {
  currency: string
  total_cost_basis: string
  total_market_value: string
  total_unrealized_pl: string
  total_unrealized_pl_pct: string | null
  total_realized_pl: string
  allocation: { symbol: string; market_value: string; allocation_pct: string }[]
  unpriced_symbols: string[]
  has_stale_prices: boolean
  total_day_change: string | null
  total_day_change_pct: string | null
  day_change_bases: DayChangeBasis[]
  day_change_unavailable_symbols: string[]
}

export interface RealizedSale {
  transaction_id: string
  symbol: string
  executed_at: string
  quantity: string
  price: string
  fee: string
  average_cost: string
  cost_basis: string
  proceeds: string
  realized_pl: string
}

export interface RealizedPl {
  currency: string
  total_realized_pl: string
  sales: RealizedSale[]
}

export function getHoldings(): Promise<Holding[]> {
  return apiGet<Holding[]>('/portfolio/holdings')
}

export function getSummary(): Promise<PortfolioSummary> {
  return apiGet<PortfolioSummary>('/portfolio/summary')
}

export function getRealizedPl(): Promise<RealizedPl> {
  return apiGet<RealizedPl>('/portfolio/realized-pl')
}
