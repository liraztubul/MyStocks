import type { ReactNode } from 'react'
import type { User } from '../api/auth'
import type { Route } from '../hooks/useHashRoute'
import { t } from '../strings'
import { Icon, type IconName } from './Icon'
import { ThemeToggle } from './ThemeToggle'

const LINKS: { route: Route; href: string; label: string; icon: IconName }[] = [
  { route: 'dashboard', href: '#/', label: t.nav.dashboard, icon: 'dashboard' },
  { route: 'transactions', href: '#/transactions', label: t.nav.transactions, icon: 'list' },
]

function NavLinks({ route, className }: { route: Route; className: string }) {
  return (
    <nav aria-label={t.nav.label} className={className}>
      {LINKS.map((link) => (
        <a key={link.route} href={link.href} aria-current={route === link.route ? 'page' : undefined}>
          <Icon name={link.icon} size={20} />
          <span>{link.label}</span>
        </a>
      ))}
    </nav>
  )
}

export function AppShell({ user, route, children }: { user: User; route: Route; children: ReactNode }) {
  return (
    <div className="app">
      <header className="app-header">
        <div className="container header-row">
          <a href="#/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <Icon name="logo" size={20} />
            </span>
            {t.appName}
          </a>
          {/* Same links twice: top tabs from tablet up, a bottom tab bar on phones. CSS shows one. */}
          <NavLinks route={route} className="top-nav" />
          <div className="header-actions">
            <span className="user-email" data-testid="user-email">
              {user.email}
            </span>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="container page">{children}</main>
      <footer className="container disclaimer">
        {t.disclaimer.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </footer>
      <NavLinks route={route} className="bottom-nav" />
    </div>
  )
}
