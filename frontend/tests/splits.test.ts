import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Split } from '../src/api/splits.ts'
import type { Transaction } from '../src/api/transactions.ts'
import { formatRatio, isReverse, ledgerRows, newYorkDay } from '../src/components/splits.ts'

function trade(id: string, executed_at: string): Transaction {
  return {
    id,
    symbol: 'AAPL',
    asset_type: 'stock',
    side: 'buy',
    quantity: '1',
    price: '100',
    fee: '0',
    currency: 'USD',
    executed_at,
    created_at: executed_at,
  }
}

function split(id: string, effective_date: string, numerator = '4', denominator = '1'): Split {
  return {
    id,
    symbol: 'AAPL',
    effective_date,
    numerator,
    denominator,
    shares_before: '1',
    shares_after: '4',
    created_at: '2026-09-20T00:00:00Z',
  }
}

test('ratios read new:old and reverse splits are recognised', () => {
  assert.equal(formatRatio(split('s', '2026-09-14')), '4:1')
  assert.equal(formatRatio(split('s', '2026-09-14', '1', '10')), '1:10')
  assert.equal(isReverse(split('s', '2026-09-14')), false)
  assert.equal(isReverse(split('s', '2026-09-14', '1', '10')), true)
  assert.equal(isReverse(split('s', '2026-09-14', '2', '3')), true)
})

test('the New York day, not the UTC one', () => {
  // 03:00 UTC on 15 Sep is 23:00 on 14 Sep in New York (EDT).
  assert.equal(newYorkDay(new Date('2026-09-15T03:00:00Z')), '2026-09-14')
  assert.equal(newYorkDay(new Date('2026-09-15T15:00:00Z')), '2026-09-15')
})

test('newest first, with a split below the trades of its own New York date', () => {
  const rows = ledgerRows(
    [
      trade('later', '2026-09-20T15:00:00Z'),
      trade('exDate', '2026-09-15T03:00:00Z'), // 14 Sep in New York: the split's day
      trade('before', '2026-09-13T15:00:00Z'),
    ],
    [split('split', '2026-09-14')],
  )
  assert.deepEqual(
    rows.map((r) => (r.kind === 'trade' ? r.trade.id : r.split.id)),
    ['later', 'exDate', 'split', 'before'],
  )
})

test('server order is kept within a day', () => {
  const rows = ledgerRows([trade('b', '2026-09-14T18:00:00Z'), trade('a', '2026-09-14T15:00:00Z')], [])
  assert.deepEqual(
    rows.map((r) => (r.kind === 'trade' ? r.trade.id : '')),
    ['b', 'a'],
  )
})
