import type { ReactNode } from 'react'
import type { User } from '../api/auth'
import type { Route } from '../hooks/useHashRoute'
import { t } from '../strings'

const LINKS: { route: Route; href: string; label: string }[] = [
  { route: 'dashboard', href: '#/', label: t.nav.dashboard },
  { route: 'transactions', href: '#/transactions', label: t.nav.transactions },
]

export function AppShell({ user, route, children }: { user: User; route: Route; children: ReactNode }) {
  return (
    <main className="wide">
      <header className="page-header">
        <h1>MyStocks</h1>
        <nav aria-label={t.nav.label} className="tabs">
          {LINKS.map((link) => (
            <a key={link.route} href={link.href} aria-current={route === link.route ? 'page' : undefined}>
              {link.label}
            </a>
          ))}
        </nav>
        <span className="muted">
          <strong data-testid="user-email">{user.email}</strong>
        </span>
      </header>
      {children}
      <footer className="disclaimer">
        {t.disclaimer.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </footer>
    </main>
  )
}
