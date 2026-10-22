import { apiGet } from './client'
import type { DayChangeBasis } from './portfolio'
import type { AssetType } from './transactions'

export interface AssetMatch {
  symbol: string
  name: string
  asset_type: AssetType
  // Ticker for stocks, CoinGecko coin id for crypto; disambiguates coins that share a ticker.
  provider_id: string
}

export interface AssetSearchResponse {
  results: AssetMatch[]
  unavailable: { asset_type: AssetType; code: string; detail: string }[]
  stock_data_available: boolean
}

export interface PriceOnDate {
  symbol: string
  asset_type: AssetType
  price: string
  currency: string
  requested_date: string
  price_date: string
  is_fallback: boolean
  kind: 'close' | 'live'
  note: string | null
}

export interface PriceOnParams {
  symbol: string
  assetType: AssetType
  date: string
  providerId: string | null
}

// The latest price for a symbol. Stocks: Finnhub through the server's 60 s cache; a blocked user
// gets 403 not_available_on_deployment before any provider call. Decimal strings throughout.
export interface LatestQuote {
  symbol: string
  asset_type: AssetType
  price: string
  currency: string
  as_of: string
  is_stale: boolean
  change: string | null
  change_pct: string | null
  change_basis: DayChangeBasis | null
  reference_at: string | null
}

export function getQuote(symbol: string, assetType: AssetType): Promise<LatestQuote> {
  return apiGet<LatestQuote>(`/assets/${encodeURIComponent(symbol)}/quote?${new URLSearchParams({ asset_type: assetType })}`)
}

export function searchAssets(query: string): Promise<AssetSearchResponse> {
  return apiGet<AssetSearchResponse>(`/assets/search?${new URLSearchParams({ q: query })}`)
}

export function getPriceOn({ symbol, assetType, date, providerId }: PriceOnParams): Promise<PriceOnDate> {
  const params = new URLSearchParams({ date, asset_type: assetType })
  if (providerId) params.set('provider_id', providerId)
  return apiGet<PriceOnDate>(`/assets/${encodeURIComponent(symbol)}/price-on?${params}`)
}
