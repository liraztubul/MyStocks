import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getHoldings, getRealizedPl, getSummary } from '../api/portfolio'

export const PORTFOLIO_KEY = ['portfolio']

// Matches the backend's 60s stock-quote cache: polling faster only re-reads the cache, and each
// stock symbol then costs at most one Finnhub call a minute (free tier: 60/min). Crypto quotes
// are reused for 5 minutes server-side, so these polls cost CoinGecko nothing in between. TanStack
// pauses interval refetches while the tab is hidden (refetchIntervalInBackground: false).
const PRICE_POLL_MS = 60_000

const livePrices = {
  staleTime: PRICE_POLL_MS,
  refetchInterval: PRICE_POLL_MS,
  refetchIntervalInBackground: false,
  // Keep showing the last render while a poll is in flight instead of flashing a spinner.
  placeholderData: keepPreviousData,
} as const

export function useHoldings() {
  return useQuery({ queryKey: [...PORTFOLIO_KEY, 'holdings'], queryFn: getHoldings, ...livePrices })
}

export function useSummary() {
  return useQuery({ queryKey: [...PORTFOLIO_KEY, 'summary'], queryFn: getSummary, ...livePrices })
}

// Realized P/L doesn't depend on prices; it only changes with the ledger, which invalidates it.
export function useRealizedPl() {
  return useQuery({ queryKey: [...PORTFOLIO_KEY, 'realized-pl'], queryFn: getRealizedPl })
}
