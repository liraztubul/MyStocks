import { useQuery } from '@tanstack/react-query'
import { getHoldings } from '../api/portfolio'

export const PORTFOLIO_KEY = ['portfolio']

export function useHoldings() {
  return useQuery({
    queryKey: [...PORTFOLIO_KEY, 'holdings'],
    queryFn: getHoldings,
    // Matches the backend's 60s live-quote cache; refetching sooner would just hit the cache.
    staleTime: 60_000,
  })
}
