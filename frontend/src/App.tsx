import { ApiError } from './api/client'
import { AppShell } from './components/AppShell'
import { useMe } from './hooks/useAuth'
import { useHashRoute } from './hooks/useHashRoute'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { TransactionsPage } from './pages/TransactionsPage'

// Auth gate instead of a router for now: /me decides whether the app or the login page renders,
// and a successful login writes the user into the /me cache, which swaps the page in place.
export function App() {
  const { data: user, error, isPending } = useMe()
  const route = useHashRoute()

  if (isPending) return <main>Loading…</main>
  if (user) {
    return (
      <AppShell user={user} route={route}>
        {route === 'transactions' ? <TransactionsPage /> : <DashboardPage />}
      </AppShell>
    )
  }
  if (error instanceof ApiError && error.status === 401) return <LoginPage />
  return <main>Could not reach the server: {error?.message}</main>
}
