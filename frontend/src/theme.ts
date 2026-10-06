export type Theme = 'light' | 'dark'

// The rule, shared with the pre-paint script in index.html (which can't import this module, so
// keep the two in sync): an explicitly stored 'light' or 'dark' wins; anything else, including
// nothing at all or the retired 'system' value, means "no choice yet" and follows the OS.
export const THEME_STORAGE_KEY = 'mystocks-theme'
// Matches --bg in index.css so the browser chrome blends into the page.
const THEME_COLOR: Record<Theme, string> = { light: '#f7f5ff', dark: '#0f0d1f' }
const DARK_QUERY = '(prefers-color-scheme: dark)'

function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark'
}

// Storage can throw (private mode, disabled cookies, sandboxed iframes); the app must still work.
export function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isTheme(stored) ? stored : null
  } catch {
    return null
  }
}

export function writeStoredTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Non-persistent is fine: the choice still applies for this page load.
  }
}

export function osTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme])
}

export function onOsThemeChange(callback: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY)
  query.addEventListener('change', callback)
  return () => query.removeEventListener('change', callback)
}
