import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import { retryDelay, retryUnlessDefinite } from './api/client'
import { App } from './App'

// Queries ride out a backend cold start (see api/client.ts); mutations are never retried
// automatically, because repeating a POST the server may already have applied isn't safe.
// Before M6 the app used hash navigation (#/transactions). Turn an old link into the real path,
// so bookmarks keep working instead of landing on the dashboard: once before the router first
// reads the URL, and again whenever only the hash changes (no page load, e.g. a pasted old link).
function redirectLegacyHash() {
  const path = /^#(\/.*)$/.exec(window.location.hash)?.[1]
  if (!path) return
  window.history.replaceState(null, '', path)
  // BrowserRouter re-reads the URL on popstate; replaceState alone doesn't fire one.
  window.dispatchEvent(new PopStateEvent('popstate'))
}
redirectLegacyHash()
window.addEventListener('hashchange', redirectLegacyHash)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: retryUnlessDefinite, retryDelay },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
