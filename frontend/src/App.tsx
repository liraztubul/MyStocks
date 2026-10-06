import { isServerWaking } from './api/client'
import { AppShell } from './components/AppShell'
import { FormError } from './components/FormError'
import { ServerWakeNotice } from './components/ServerWakeNotice'
import { useMe } from './hooks/useAuth'
import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router'
import { RowsSkeleton } from './components/Skeleton'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { t } from './strings'

// The auth gate sits outside the routes: /me decides whether the app or the login page renders
// (user, null for logged out), and a successful login writes the user into the /me cache, which
// swaps the page in place. The URL never changes, so a deep link survives logging in. The boot
// and error screens only ever show before the first answer.
// Its own chunk: the asset page will carry the chart library, which other pages don't need.
const AssetPage = lazy(() => import('./pages/AssetPage'))

// The page was /holdings/:symbol before it covered assets you don't hold; old links still work.
function LegacyHoldingRedirect() {
  const { symbol = '' } = useParams()
  return <Navigate to={`/assets/${encodeURIComponent(symbol)}`} replace />
}

export function App() {
  const { data: user, error, isPending } = useMe()

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
      <AppShell user={user}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route
            path="/assets/:symbol"
            element={
              <Suspense fallback={<RowsSkeleton rows={4} />}>
                <AssetPage />
              </Suspense>
            }
          />
          <Route path="/holdings/:symbol" element={<LegacyHoldingRedirect />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
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
