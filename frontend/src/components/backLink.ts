// Where the asset page's "Back" link goes: the watchlist when the page was opened from it (router
// state, set by the watchlist's links), otherwise the dashboard. Any other or missing state, e.g.
// a pasted URL or a new tab, falls back to the dashboard.
export type BackTarget = 'watchlist' | 'dashboard'

export const FROM_WATCHLIST = { from: 'watchlist' } as const

export function backTarget(state: unknown): BackTarget {
  if (typeof state === 'object' && state !== null && (state as { from?: unknown }).from === 'watchlist') {
    return 'watchlist'
  }
  return 'dashboard'
}
