import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { useDelayedFlag } from '../hooks/useDelayedFlag'
import { t } from '../strings'

// Longer than an awake backend ever takes: its slowest path is a portfolio refresh waiting on
// the 5 s market-data timeout. Past this, a sleeping backend is the likely cause.
const SLOW_REQUEST_MS = 8_000

// Shown wherever a request is slow, whichever request it is: a sleeping free-tier backend is the
// normal first-visit case, not an error. Queries keep retrying underneath (see api/client.ts).
export function ServerWakeNotice() {
  const busy = useIsFetching() + useIsMutating() > 0
  const slow = useDelayedFlag(busy, SLOW_REQUEST_MS)
  if (!slow) return null
  return (
    <div className="wake-notice" role="status">
      <span className="wake-spinner" aria-hidden="true" />
      <div>
        <strong>{t.wake.title}</strong> <span>{t.wake.body}</span>
      </div>
    </div>
  )
}
