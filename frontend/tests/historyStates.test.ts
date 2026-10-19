import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isSplitAdjusted, retryMinutes, unavailableMessage } from '../src/components/historyStates.ts'

test('every unavailable reason has its own message', () => {
  assert.equal(unavailableMessage('not_available_on_deployment'), 'notOnDeployment')
  assert.equal(unavailableMessage('provider_not_configured'), 'providerNotConfigured')
  assert.equal(unavailableMessage('rate_limited'), 'rateLimited')
  assert.equal(unavailableMessage('provider_unavailable'), 'providerUnavailable')
})

test('a missing reason reads as the provider being unavailable', () => {
  assert.equal(unavailableMessage(null), 'providerUnavailable')
})

test('the wait is whole minutes, rounded up, at least one', () => {
  assert.equal(retryMinutes(60), 1)
  assert.equal(retryMinutes(61), 2)
  assert.equal(retryMinutes(5), 1)
  assert.equal(retryMinutes(15 * 60), 15)
})

test('an unknown wait has no number', () => {
  assert.equal(retryMinutes(null), null)
  assert.equal(retryMinutes(0), null)
  assert.equal(retryMinutes(-3), null)
})

test('a price is adjusted only when it differs as a decimal', () => {
  assert.equal(isSplitAdjusted('2470', '1235.0000000000'), true)
  assert.equal(isSplitAdjusted('1235', '1235.0000000000'), false)
  assert.equal(isSplitAdjusted('0.1', '0.10'), false)
})
