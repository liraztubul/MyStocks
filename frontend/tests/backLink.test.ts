import assert from 'node:assert/strict'
import { test } from 'node:test'
import { FROM_WATCHLIST, backTarget } from '../src/components/backLink.ts'
import { assetPath } from '../src/components/assetLinks.ts'

test('opened from the watchlist: back goes to the watchlist', () => {
  assert.equal(backTarget(FROM_WATCHLIST), 'watchlist')
  assert.equal(backTarget({ from: 'watchlist', extra: 1 }), 'watchlist')
})

test('anything else falls back to the dashboard', () => {
  for (const state of [null, undefined, 'watchlist', 42, {}, { from: 'dashboard' }, { from: ['watchlist'] }]) {
    assert.equal(backTarget(state), 'dashboard')
  }
})

test('a watchlist row links to its exact coin when the coin is known', () => {
  assert.equal(assetPath('CAT', 'crypto', 'simon-s-cat'), '/assets/CAT?type=crypto&id=simon-s-cat')
  assert.equal(assetPath('CAT', 'crypto', null), '/assets/CAT?type=crypto')
  assert.equal(assetPath('BRK.B', 'stock'), '/assets/BRK.B?type=stock')
})
