// What the stock page's "Latest price" line shows, from the quote query's outcome.
// - hidden: not a stock, stock data not available to this user (the endpoint's 403, or the chart
//   already said so), or an unknown ticker (404): the page says why elsewhere.
// - loading: first fetch in flight (a placeholder keeps the layout still).
// - price: a quote, fresh or the last saved one marked stale (it carries its own time).
// - unavailable: any other failure with nothing to show.
export type LatestPriceState = 'hidden' | 'loading' | 'price' | 'unavailable'

export interface QuoteOutcome {
  isStock: boolean
  blockedByChart: boolean
  hasData: boolean
  pending: boolean
  errorStatus: number | null
  errorCode: string | null
}

export function latestPriceState(o: QuoteOutcome): LatestPriceState {
  if (!o.isStock || o.blockedByChart) return 'hidden'
  if (o.errorCode === 'not_available_on_deployment' || o.errorStatus === 403 || o.errorStatus === 404) {
    return 'hidden'
  }
  if (o.hasData) return 'price'
  if (o.pending) return 'loading'
  return 'unavailable'
}

// "14:30" in New York, whatever the viewer's own time zone.
export function newYorkTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleTimeString(locale, {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/New_York',
  })
}
