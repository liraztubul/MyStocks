import { useEffect, useState } from 'react'
import {
  applyTheme,
  onSystemThemeChange,
  readPreference,
  resolveTheme,
  writePreference,
  type ThemePreference,
} from '../theme'

export function useTheme() {
  // index.html already applied this preference before first paint; React just takes over.
  const [preference, setPreference] = useState<ThemePreference>(readPreference)

  useEffect(() => {
    applyTheme(resolveTheme(preference))
    if (preference !== 'system') return
    return onSystemThemeChange(() => applyTheme(resolveTheme('system')))
  }, [preference])

  useEffect(() => {
    // Colour transitions switch on only after first render, so loading the page doesn't
    // animate from the default colours into the saved theme.
    const frame = requestAnimationFrame(() => document.documentElement.classList.add('theme-ready'))
    return () => cancelAnimationFrame(frame)
  }, [])

  function choose(next: ThemePreference) {
    writePreference(next)
    setPreference(next)
  }

  return { preference, choose }
}
