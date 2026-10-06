import { t } from '../strings'
import { ApiError, isServerWaking } from './client'

// What to tell the user when a ledger write fails. Only 400/422 are "fix your input": the server
// text is shown as-is because it names the exact problem. A 401 never reaches here; the mutation
// hooks hand it to useExpireSession, which swaps to the login page.
export function writeErrorMessage(error: Error): string {
  if (isServerWaking(error)) return t.wake.retryAction
  if (!(error instanceof ApiError)) return t.writeErrors.failed(error.message)
  switch (error.status) {
    case 400:
    case 422:
      return t.writeErrors.rejected(error.message)
    case 403:
      return t.writeErrors.forbidden
    case 429:
      return t.writeErrors.tooMany(error.retryAfter)
    default:
      return t.writeErrors.failed(error.message)
  }
}

export function isSessionExpired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}
