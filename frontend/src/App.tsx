import { isServerWaking } from './api/client'
import { AppShell } from './components/AppShell'
import { FormError } from './components/FormError'
import { ServerWakeNotice } from './components/ServerWakeNotice'
import { useMe } from './hooks/useAuth'
import { useHashRoute } from './hooks/useHashRoute'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { t } from './strings'

// Auth gate instead of a router for now: /me decides whether the app or the login page renders
// (user, null for logged out), and a successful login writes the user into the /me cache, which
// swaps the page in place. The boot and error screens only ever show before the first answer.
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
  // Logged out (a 401 from /me, or useExpireSession after a write). Checked before the error
  // branch: once we know the answer is "logged out", a failed background refetch (say, the server
  // fell asleep) must not replace a half-filled login form with an error screen.
  if (user === null) return <LoginPage />
  return (
    <main className="boot">
      <FormError>{isServerWaking(error) ? t.wake.gaveUp : t.common.serverUnreachable(error?.message ?? '')}</FormError>
    </main>
  )
}
