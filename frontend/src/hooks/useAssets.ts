import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getPriceOn, getQuote, searchAssets, type PriceOnParams } from '../api/assets'

export function useAssetSearch(query: string) {
  const q = query.trim()
  return useQuery({
    queryKey: ['assets', 'search', q.toLowerCase()],
    queryFn: () => searchAssets(q),
    enabled: q.length > 0,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
    // Upstream rate limits are tight; a failed search should surface, not be retried into them.
    retry: false,
  })
}

export function usePriceOn(params: PriceOnParams | null) {
  return useQuery({
    queryKey: ['assets', 'price-on', params],
    queryFn: () => getPriceOn(params!),
    enabled: params !== null,
    staleTime: 60_000,
    retry: false,
  })
}

// The stock page's "Latest price": every 60 s while the tab is visible (the server's quote cache
// is 60 s), paused when hidden, no refetch on focus. No automatic retry: the app's default would
// treat a provider outage's 503 as a waking server and retry every few seconds; the next poll is
// the retry. In memory only, like every query here.
export function useLatestQuote(symbol: string, enabled: boolean) {
  return useQuery({
    queryKey: ['assets', 'quote', 'stock', symbol],
    queryFn: () => getQuote(symbol, 'stock'),
    enabled,
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    retry: false,
  })
}
