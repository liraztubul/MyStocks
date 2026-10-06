import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getHistory, type HistoryParams } from '../api/history'

export function useAssetHistory(params: HistoryParams) {
  return useQuery({
    queryKey: ['history', params],
    queryFn: () => getHistory(params),
    // Daily closes change once a day; the server's cache does the real work.
    staleTime: 5 * 60_000,
    // Keep the previous range on screen while the next one loads, instead of a blank chart.
    placeholderData: keepPreviousData,
    // Retry policy: the app default (waits out a sleeping server, gives up on 4xx).
  })
}
