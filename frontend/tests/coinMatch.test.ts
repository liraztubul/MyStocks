// Node's built-in test runner with type stripping: no test dependency. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { exactSuggestion } from '../src/components/coinMatch.ts'

const coin = (symbol: string, name: string, id = name.toLowerCase()) => ({ provider_id: id, symbol, name })
const BTC = coin('BTC', 'Bitcoin')
const BCH = coin('BCH', 'Bitcoin Cash')
const WBTC = coin('WBTC', 'Wrapped Bitcoin')
const DAI = coin('DAI', 'Dai')
const PDAI = coin('DAI', 'DAI on PulseChain', 'pdai')

test('the name, any case and padding, picks that coin', () => {
  assert.equal(exactSuggestion('  bitcoin ', [BTC, BCH, WBTC]), BTC)
  assert.equal(exactSuggestion('BITCOIN', [BCH, BTC]), BTC)
})

test('the ticker picks that coin', () => {
  assert.equal(exactSuggestion('btc', [BTC, BCH]), BTC)
  assert.equal(exactSuggestion('WBTC', [BTC, WBTC]), WBTC)
})

test('a prefix or partial name is not an exact match', () => {
  assert.equal(exactSuggestion('bit', [BTC, BCH]), null)
  assert.equal(exactSuggestion('bitcoin c', [BTC, BCH]), null)
})

test('a ticker shared by several coins is left to the server', () => {
  assert.equal(exactSuggestion('dai', [DAI, PDAI]), null)
})

test("a ticker beats another coin's identical name", () => {
  const named = coin('XYZ', 'Velo', 'named-velo')
  const ticker = coin('VELO', 'Velodrome Finance')
  assert.equal(exactSuggestion('velo', [named, ticker]), ticker)
})

test('two coins with the same name and different tickers: no pick', () => {
  assert.equal(exactSuggestion('usda', [coin('USDA1', 'USDa', 'a'), coin('USDA2', 'usda', 'b')]), null)
})

test('nothing typed or nothing listed', () => {
  assert.equal(exactSuggestion('   ', [BTC]), null)
  assert.equal(exactSuggestion('btc', []), null)
})
