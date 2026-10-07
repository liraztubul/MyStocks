import { useEffect } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addToWatchlist, listWatchlist, removeFromWatchlist } from '../api/watchlist'
import { isSessionExpired } from '../api/writeErrors'
import { useExpireSession } from './useAuth'

const WATCHLIST_KEY = ['watchlist']

// CoinGecko's own cache is 30-60 s and ours 60 s, so polling faster would only re-read it.
// Interval refetches pause while the tab is hidden.
const POLL_MS = 60_000

// A 401 here means the session expired while the page was open: swap to the login page.
export function useWatchlist() {
  const expire = useExpireSession()
  const query = useQuery({
    queryKey: WATCHLIST_KEY,
    queryFn: listWatchlist,
    staleTime: POLL_MS,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
  useEffect(() => {
    if (isSessionExpired(query.error)) expire()
  }, [query.error, expire])
  return query
}

function useWatchlistWrite<T, R>(mutationFn: (arg: T) => Promise<R>) {
  const queryClient = useQueryClient()
  const expire = useExpireSession()
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: WATCHLIST_KEY }),
    onError: (error) => {
      if (isSessionExpired(error)) expire()
    },
  })
}

export function useAddToWatchlist() {
  return useWatchlistWrite(addToWatchlist)
}

export function useRemoveFromWatchlist() {
  return useWatchlistWrite(removeFromWatchlist)
}
