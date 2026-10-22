import assert from 'node:assert/strict'
import { test } from 'node:test'
import { latestPriceState, newYorkTime, type QuoteOutcome } from '../src/components/latestPrice.ts'

const base: QuoteOutcome = {
  isStock: true,
  blockedByChart: false,
  hasData: false,
  pending: false,
  errorStatus: null,
  errorCode: null,
}

test('a quote is shown, fresh or stale', () => {
  assert.equal(latestPriceState({ ...base, hasData: true }), 'price')
  // A later poll failing keeps the last quote on screen (it shows its own time).
  assert.equal(latestPriceState({ ...base, hasData: true, errorStatus: 503 }), 'price')
})

test('nothing is shown for crypto, a blocked user or an unknown ticker', () => {
  assert.equal(latestPriceState({ ...base, isStock: false, hasData: true }), 'hidden')
  assert.equal(latestPriceState({ ...base, blockedByChart: true }), 'hidden')
  assert.equal(latestPriceState({ ...base, errorStatus: 403, errorCode: 'not_available_on_deployment' }), 'hidden')
  assert.equal(latestPriceState({ ...base, errorStatus: 404, errorCode: 'symbol_not_found' }), 'hidden')
})

test('first load shows a placeholder; a failure with nothing saved says unavailable', () => {
  assert.equal(latestPriceState({ ...base, pending: true }), 'loading')
  assert.equal(latestPriceState({ ...base, errorStatus: 503, errorCode: 'provider_unavailable' }), 'unavailable')
  assert.equal(latestPriceState({ ...base, errorStatus: 503, errorCode: 'rate_limited' }), 'unavailable')
})

test('the time is New York time, in summer and in winter', () => {
  assert.equal(newYorkTime('2026-07-15T18:30:00Z', 'en-GB'), '14:30') // EDT, UTC-4
  assert.equal(newYorkTime('2026-01-15T18:30:00Z', 'en-GB'), '13:30') // EST, UTC-5
  assert.equal(newYorkTime('2026-07-15T18:30:00Z', 'en-US'), '2:30 PM') // the app's locale
})
