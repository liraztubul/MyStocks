import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getHistory, type HistoryParams } from '../api/history'

export function useAssetHistory(params: HistoryParams) {
  return useQuery({
    queryKey: ['history', params],
    queryFn: () => getHistory(params),
    // Daily closes change once a day. A stock range costs a Tiingo request each time it is
    // fetched (nothing is stored server-side), so ranges are reused for the visit: in memory
    // only (this query cache is never persisted), no refetch on focus, no polling.
    staleTime: 60 * 60_000,
    refetchOnWindowFocus: false,
    // Keep the previous range on screen while the next one loads, instead of a blank chart.
    placeholderData: keepPreviousData,
    // Retry policy: the app default (waits out a sleeping server, gives up on 4xx). A spent
    // request budget or a provider outage is a 200 with a reason, so it's never retried.
  })
}
