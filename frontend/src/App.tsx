import { ApiError } from './api/client'
import { useMe } from './hooks/useAuth'
import { LoginPage } from './pages/LoginPage'
import { TransactionsPage } from './pages/TransactionsPage'

// Auth gate instead of a router for now: /me decides which page renders, and a successful
// login writes the user into the /me cache, which swaps the page without a navigation.
export function App() {
  const { data: user, error, isPending } = useMe()

  if (isPending) return <main>Loading…</main>
  if (user) return <TransactionsPage user={user} />
  if (error instanceof ApiError && error.status === 401) return <LoginPage />
  return <main>Could not reach the server: {error?.message}</main>
}
