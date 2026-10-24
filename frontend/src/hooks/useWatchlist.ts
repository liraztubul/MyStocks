import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addToWatchlist, listWatchlist, removeFromWatchlist } from '../api/watchlist'

const WATCHLIST_KEY = ['watchlist']

// The server reuses a crypto quote for 5 minutes (CRYPTO_QUOTE_TTL_SECONDS, sized for CoinGecko's
// monthly cap), so polling faster would only re-read its cache. Paused while the tab is hidden.
const POLL_MS = 5 * 60_000

export function useWatchlist() {
  return useQuery({
    queryKey: WATCHLIST_KEY,
    queryFn: listWatchlist,
    staleTime: POLL_MS,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
}

function useWatchlistWrite<T, R>(mutationFn: (arg: T) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: WATCHLIST_KEY }),
  })
}

export function useAddToWatchlist() {
  return useWatchlistWrite(addToWatchlist)
}

export function useRemoveFromWatchlist() {
  return useWatchlistWrite(removeFromWatchlist)
}
