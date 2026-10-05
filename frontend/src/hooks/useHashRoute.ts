import { useEffect, useState } from 'react'

export type Route = 'dashboard' | 'transactions'

function routeFromHash(): Route {
  return window.location.hash === '#/transactions' ? 'transactions' : 'dashboard'
}

// Temporary two-view navigation; M6 replaces this with a real router (see ROADMAP.md).
export function useHashRoute(): Route {
  const [route, setRoute] = useState(routeFromHash)
  useEffect(() => {
    const onChange = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
