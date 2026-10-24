import Big from 'big.js'
import type { Split } from '../api/splits'
import type { Transaction } from '../api/transactions'

// "4:1": new shares first, as splits are usually written. Shown inside <bdi dir="ltr"> so a
// right-to-left page never turns it into "1:4".
export function formatRatio(split: Pick<Split, 'numerator' | 'denominator'>): string {
  return `${split.numerator}:${split.denominator}`
}

export function isReverse(split: Pick<Split, 'numerator' | 'denominator'>): boolean {
  return Big(split.numerator).lt(split.denominator)
}

const NEW_YORK_DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

// "YYYY-MM-DD" in New York: the calendar a split's date and the server's checks use.
export function newYorkDay(at: Date): string {
  return NEW_YORK_DAY.format(at)
}

export type LedgerRow = { kind: 'trade'; trade: Transaction } | { kind: 'split'; split: Split }

// Newest first, the way the server lists trades. A split counts before the trades of its own
// New York date, so in this newest-first list it sits below them.
export function ledgerRows(transactions: Transaction[], splits: Split[]): LedgerRow[] {
  const rows = [
    ...transactions.map((trade, i) => ({
      key: [newYorkDay(new Date(trade.executed_at)), 1, -i] as const,
      row: { kind: 'trade', trade } as LedgerRow,
    })),
    ...splits.map((split, i) => ({
      key: [split.effective_date, 0, -i] as const,
      row: { kind: 'split', split } as LedgerRow,
    })),
  ]
  rows.sort((a, b) => {
    for (let k = 0; k < 3; k++) {
      if (a.key[k] !== b.key[k]) return a.key[k] < b.key[k] ? 1 : -1
    }
    return 0
  })
  return rows.map((r) => r.row)
}
