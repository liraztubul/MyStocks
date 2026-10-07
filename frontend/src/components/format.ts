import Big from 'big.js'
import { t } from '../strings'
import { chartDecimals } from './chartData'

function group(fixed: string): string {
  const [whole, fraction] = fixed.split('.')
  const sign = whole.startsWith('-') ? '-' : ''
  const digits = whole.replace('-', '').replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${sign}${digits}${fraction ? `.${fraction}` : ''}`
}

// Sub-dollar prices (most crypto) keep their digits; 2 places would show them as 0.00.
export function formatPrice(value: string): string {
  return Big(value).abs().lt(1) ? value : group(Big(value).toFixed(2))
}

// A live quote, with the chart's precision rule: about four significant digits below 1 (a
// micro-priced coin never shows as 0.00), two places from 1 up. Big rounds the exact string.
export function formatQuotePrice(value: string): string {
  return group(Big(value).toFixed(chartDecimals(Number(value))))
}

export function formatMoney(value: string): string {
  return group(Big(value).toFixed(2))
}

export function formatSignedMoney(value: string): string {
  const formatted = formatMoney(value)
  return Big(value).gt(0) ? `+${formatted}` : formatted
}

export function formatSignedPercent(value: string): string {
  const fixed = Big(value).toFixed(2)
  return `${Big(value).gt(0) ? '+' : ''}${fixed}%`
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(t.locale, { dateStyle: 'medium', timeStyle: 'short' })
}

// A calendar day ("2026-09-04", a bar's or trade's date). Formatted in UTC: parsed as UTC
// midnight, it would show as the previous day in browsers west of UTC otherwise.
export function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(t.locale, { dateStyle: 'medium', timeZone: 'UTC' })
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(t.locale, { dateStyle: 'medium' })
}

// A stock's reference_at is 00:00 New York on its session; render that date in New York so a
// viewer west or east of it doesn't see the neighbouring day.
export function formatSessionDate(iso: string): string {
  return new Date(iso).toLocaleDateString(t.locale, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: 'America/New_York',
  })
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
]

// "3 minutes ago". A timestamp slightly ahead of this device's clock reads as just now.
export function formatRelative(iso: string, now: number): string {
  const seconds = Math.min(0, Math.round((new Date(iso).getTime() - now) / 1000))
  const format = new Intl.RelativeTimeFormat(t.locale, { numeric: 'auto' })
  for (const [unit, size] of RELATIVE_UNITS) {
    if (-seconds >= size) return format.format(Math.trunc(seconds / size), unit)
  }
  return t.watchlist.justNow
}
