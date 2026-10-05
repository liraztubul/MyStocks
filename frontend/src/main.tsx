import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { retryDelay, retryUnlessDefinite } from './api/client'
import { App } from './App'

// Queries ride out a backend cold start (see api/client.ts); mutations are never retried
// automatically, because repeating a POST the server may already have applied isn't safe.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: retryUnlessDefinite, retryDelay },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
