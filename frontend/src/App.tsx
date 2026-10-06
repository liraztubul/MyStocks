import { ApiError, isServerWaking } from './api/client'
import { AppShell } from './components/AppShell'
import { FormError } from './components/FormError'
import { ServerWakeNotice } from './components/ServerWakeNotice'
import { useMe } from './hooks/useAuth'
import { useHashRoute } from './hooks/useHashRoute'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { t } from './strings'

// Auth gate instead of a router for now: /me decides whether the app or the login page renders,
// and a successful login writes the user into the /me cache, which swaps the page in place.
export function App() {
  const { data: user, error, isPending } = useMe()
  const route = useHashRoute()

  // The first request of a visit is the one that usually meets a sleeping backend.
  if (isPending) {
    return (
      <main className="boot">
        <p className="muted">{t.common.loading}</p>
        <ServerWakeNotice />
      </main>
    )
  }
  if (user) {
    return (
      <AppShell user={user} route={route}>
        {route === 'transactions' ? <TransactionsPage /> : <DashboardPage />}
      </AppShell>
    )
  }
  // null (rather than an error) means a write found the session expired; see useExpireSession.
  if (user === null || (error instanceof ApiError && error.status === 401)) return <LoginPage />
  return (
    <main className="boot">
      <FormError>{isServerWaking(error) ? t.wake.gaveUp : t.common.serverUnreachable(error?.message ?? '')}</FormError>
    </main>
  )
}
