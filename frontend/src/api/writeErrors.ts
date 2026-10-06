import { t } from '../strings'
import { ApiError, isServerWaking } from './client'

// What to tell the user when a ledger write fails. Only 400/422 are "fix your input": the server
// text is shown as-is because it names the exact problem. A 401 never reaches here; the mutation
// hooks hand it to useExpireSession, which swaps to the login page.
// Stock market data this deployment may not show this user (see backend app.market_data.access):
// actions answer 403 with this code, views return the data with prices null and the same code.
export const NOT_AVAILABLE_ON_DEPLOYMENT = 'not_available_on_deployment'

export function isNotAvailableOnDeployment(error: unknown): boolean {
  return error instanceof ApiError && error.code === NOT_AVAILABLE_ON_DEPLOYMENT
}

export function writeErrorMessage(error: Error): string {
  if (isServerWaking(error)) return t.wake.retryAction
  if (!(error instanceof ApiError)) return t.writeErrors.failed(error.message)
  // A specific, expected reason beats the generic "not allowed" for its 403.
  if (isNotAvailableOnDeployment(error)) return t.stockData.notAvailable
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
