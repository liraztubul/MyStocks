import { keepPreviousData, queryOptions, useQuery } from '@tanstack/react-query'
import { suggestCoins } from '../api/coins'

export const MIN_SUGGEST_LENGTH = 2

// Answered from the server's local coin index: no provider call per keystroke. A query whose
// answer is no longer wanted is cancelled (TanStack aborts the signal once nobody observes it).
export function coinSuggestQuery(query: string) {
  const q = query.trim()
  return queryOptions({
    queryKey: ['coins', 'suggest', q.toLowerCase()],
    queryFn: ({ signal }) => suggestCoins(q, signal),
    staleTime: 5 * 60_000,
    retry: false,
  })
}

export function useCoinSuggest(query: string) {
  return useQuery({
    ...coinSuggestQuery(query),
    enabled: query.trim().length >= MIN_SUGGEST_LENGTH,
    // The previous suggestions stay up while the next ones load, so the list doesn't flicker.
    placeholderData: keepPreviousData,
  })
}
