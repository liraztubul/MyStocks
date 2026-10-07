import type { ReactNode } from 'react'
import type { User } from '../api/auth'
import { Link, NavLink } from 'react-router'
import { t } from '../strings'
import { Icon, type IconName } from './Icon'
import { Ledgie } from './Ledgie'
import { ServerWakeNotice } from './ServerWakeNotice'
import { ThemeToggle } from './ThemeToggle'

const LINKS: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: t.nav.dashboard, icon: 'dashboard' },
  { to: '/transactions', label: t.nav.transactions, icon: 'list' },
  { to: '/watchlist', label: t.nav.watchlist, icon: 'eye' },
]

// NavLink sets aria-current="page" on the active link, which the existing CSS styles. `end` keeps
// "/" from matching every path.
function NavLinks({ className }: { className: string }) {
  return (
    <nav aria-label={t.nav.label} className={className}>
      {LINKS.map((link) => (
        <NavLink key={link.to} to={link.to} end>
          <Icon name={link.icon} size={20} />
          <span>{link.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell({ user, children }: { user: User; children: ReactNode }) {
  return (
    <div className="app">
      <header className="app-header">
        <div className="container header-row">
          <Link to="/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <Ledgie pose="mark" size={30} />
            </span>
            {t.appName}
          </Link>
          {/* Same links twice: top tabs from tablet up, a bottom tab bar on phones. CSS shows one. */}
          <NavLinks className="top-nav" />
          <div className="header-actions">
            <span className="user-email" data-testid="user-email">
              {user.email}
            </span>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="container page">
        <ServerWakeNotice />
        {children}
      </main>
      <footer className="container disclaimer">
        {t.disclaimer.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <p>
          {t.attribution.coingeckoScope}
          {/* no-referrer: don't tell the provider which page (e.g. /assets/BTC) linked to it. */}
          <a href={t.attribution.coingeckoUrl} rel="noreferrer" referrerPolicy="no-referrer">
            {t.attribution.coingecko}
          </a>
        </p>
      </footer>
      <NavLinks className="bottom-nav" />
    </div>
  )
}
