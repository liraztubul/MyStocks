import { apiGet } from './client'

export interface CoinSuggestion {
  // The CoinGecko coin id: sent as the explicit id, so adding needs no lookup.
  provider_id: string
  symbol: string
  name: string
  market_cap_rank: number | null
}

export interface CoinSuggestResponse {
  results: CoinSuggestion[]
  // Set when the index can't answer (empty, loading or too old); null when it answered.
  reason: 'coin_index_loading' | 'coin_index_unavailable' | null
}

export function suggestCoins(query: string, signal?: AbortSignal): Promise<CoinSuggestResponse> {
  return apiGet<CoinSuggestResponse>(`/coins/suggest?${new URLSearchParams({ q: query })}`, signal)
}
