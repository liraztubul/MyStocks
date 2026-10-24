import { MutationCache, QueryCache } from '@tanstack/react-query'

// Session rules shared by the query client and the auth hooks; pure, so tests run them directly.

// A 401 from login, register or /me is an answer about credentials ("wrong password", "not
// logged in"), not a session that just expired; every auth request's key starts with 'auth'.
export function shouldExpireOn401(key: readonly unknown[] | undefined): boolean {
  return key?.[0] !== 'auth'
}

// Any other 401, from a query or a write, means the cookie stopped working mid-visit.
export function sessionCaches(isExpired: (error: unknown) => boolean, expire: () => void) {
  return {
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (isExpired(error) && shouldExpireOn401(query.queryKey)) expire()
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (isExpired(error) && shouldExpireOn401(mutation.options.mutationKey)) expire()
      },
    }),
  }
}

// What one tab tells the others over BroadcastChannel; anything else is ignored.
export type AuthMessage = 'logout' | 'login'

export function parseAuthMessage(data: unknown): AuthMessage | null {
  return data === 'logout' || data === 'login' ? data : null
}

// /me answered with nobody, or with someone else, where a user was shown: whatever is cached
// belongs to the previous session.
export function sessionEnded(previous: { id: string } | null | undefined, next: { id: string } | null | undefined): boolean {
  if (!previous || next === undefined) return false
  return next === null || next.id !== previous.id
}
