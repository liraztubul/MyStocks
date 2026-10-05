import Big from 'big.js'
import { t } from '../strings'

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

export function gainClass(value: string | null): string | undefined {
  if (value === null) return undefined
  const amount = Big(value)
  return amount.gt(0) ? 'gain' : amount.lt(0) ? 'loss' : undefined
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(t.locale, { dateStyle: 'medium', timeStyle: 'short' })
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
