import { t } from '../strings'

// The only place a price string becomes a JavaScript number to draw with (formatQuotePrice also
// reads one, only to choose a number of decimal places). The chart library draws with
// floats, which is fine for pixels: a double keeps 15-17 significant digits, far below what a
// pixel can show, and these numbers never flow back into a calculation or a request. Tables,
// captions and tooltips keep using the API's exact strings.
export function toChartPoint(date: string, value: string): { time: string; value: number } {
  return { time: date, value: Number(value) }
}

// Decimal places that show about four significant digits of a sub-dollar price: 0.5 -> 4 places,
// 0.00001234 -> 8 places. Two places from 1 upward, like the rest of the app.
export function chartDecimals(price: number): number {
  const magnitude = Math.abs(price)
  if (magnitude >= 1 || magnitude === 0) return 2
  return Math.min(18, Math.max(2, 3 - Math.floor(Math.log10(magnitude))))
}

// One precision for the whole chart, from its smallest close, so every axis label has the same
// number of decimals (0.00000900 next to 0.00001200, not 0.000009000).
export function chartScale(prices: number[]): { decimals: number; minMove: number } {
  const positive = prices.filter((p) => p > 0)
  const decimals = positive.length === 0 ? 2 : chartDecimals(Math.min(...positive))
  return { decimals, minMove: 10 ** -decimals }
}

// Axis and crosshair labels. The library's default (2 places) would show a micro-priced coin
// as 0.00; this keeps its significant digits.
export function chartPriceFormatter(decimals: number): (price: number) => string {
  if (decimals === 2) {
    return (price) => price.toLocaleString(t.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return (price) => price.toFixed(decimals)
}
