import type { DayChangeBasis } from '../api/portfolio'
import { t } from '../strings'
import { formatDateTime, formatSessionDate } from './format'

export function basisLabel(basis: DayChangeBasis): string {
  return basis === 'since_previous_close' ? t.dayChange.sincePreviousClose : t.dayChange.rolling24h
}

export function referenceLabel(basis: DayChangeBasis, referenceAt: string): string {
  return basis === 'since_previous_close'
    ? t.dayChange.stockReference(formatSessionDate(referenceAt))
    : t.dayChange.cryptoReference(formatDateTime(referenceAt))
}
