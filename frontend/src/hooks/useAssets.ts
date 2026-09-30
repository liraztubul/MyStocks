import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getPriceOn, searchAssets, type PriceOnParams } from '../api/assets'

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
