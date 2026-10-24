import assert from 'node:assert/strict'
import { test } from 'node:test'
import { QueryClient } from '@tanstack/react-query'
import { parseAuthMessage, sessionCaches, sessionEnded, shouldExpireOn401 } from '../src/api/session.ts'

class FakeApiError extends Error {
  readonly status: number
  constructor(status: number) {
    super(`status ${status}`)
    this.status = status
  }
}

const isExpired = (error: unknown) => error instanceof FakeApiError && error.status === 401

function client(onExpire: () => void) {
  return new QueryClient({
    ...sessionCaches(isExpired, onExpire),
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

async function failQuery(qc: QueryClient, key: unknown[], status: number) {
  await qc
    .fetchQuery({
      queryKey: key,
      queryFn: () => {
        throw new FakeApiError(status)
      },
    })
    .catch(() => undefined)
}

async function failMutation(qc: QueryClient, key: unknown[] | undefined, status: number) {
  const mutation = qc.getMutationCache().build(qc, {
    mutationKey: key,
    mutationFn: () => Promise.reject(new FakeApiError(status)),
  })
  await mutation.execute(undefined).catch(() => undefined)
}

test('a 401 from a private query or write expires the session', async () => {
  let expired = 0
  const qc = client(() => expired++)
  await failQuery(qc, ['watchlist'], 401)
  await failMutation(qc, undefined, 401)
  assert.equal(expired, 2)
})

test('a 401 from login, register or /me does not say "session expired"', async () => {
  let expired = 0
  const qc = client(() => expired++)
  await failMutation(qc, ['auth', 'login'], 401)
  await failMutation(qc, ['auth', 'register'], 401)
  await failQuery(qc, ['auth', 'me'], 401)
  assert.equal(expired, 0)
})

test('other failures do not expire the session', async () => {
  let expired = 0
  const qc = client(() => expired++)
  await failQuery(qc, ['portfolio'], 403)
  await failMutation(qc, undefined, 503)
  assert.equal(expired, 0)
})

test('only auth keys are excluded', () => {
  assert.equal(shouldExpireOn401(['auth', 'logout']), false)
  assert.equal(shouldExpireOn401(['portfolio']), true)
  assert.equal(shouldExpireOn401(['asset-history', 'auth']), true)
  assert.equal(shouldExpireOn401(undefined), true)
})

test('only known messages cross between tabs', () => {
  assert.equal(parseAuthMessage('logout'), 'logout')
  assert.equal(parseAuthMessage('login'), 'login')
  assert.equal(parseAuthMessage({ type: 'logout' }), null)
  assert.equal(parseAuthMessage(null), null)
})

test('the session ended when /me turns from a user to nobody or someone else', () => {
  const alice = { id: 'a' }
  assert.equal(sessionEnded(alice, null), true)
  assert.equal(sessionEnded(alice, { id: 'b' }), true)
  assert.equal(sessionEnded(alice, { id: 'a' }), false)
  assert.equal(sessionEnded(null, alice), false) // a login
  assert.equal(sessionEnded(undefined, null), false) // the first answer
  assert.equal(sessionEnded(alice, undefined), false) // removed from the cache, not an answer
})
