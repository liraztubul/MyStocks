import { useEffect, useState } from 'react'
import { applyTheme, onOsThemeChange, osTheme, readStoredTheme, writeStoredTheme, type Theme } from '../theme'

export function useTheme() {
  // index.html already applied this before first paint; React just takes over.
  const [stored, setStored] = useState<Theme | null>(readStoredTheme)
  const [os, setOs] = useState<Theme>(osTheme)
  const theme = stored ?? os

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  // Until the user picks one, the page keeps following the OS (e.g. an automatic switch to dark
  // at sunset). After an explicit choice, OS changes are ignored.
  useEffect(() => {
    if (stored !== null) return
    return onOsThemeChange(() => setOs(osTheme()))
  }, [stored])

  useEffect(() => {
    // Colour transitions switch on only after first render, so loading the page doesn't
    // animate from the default colours into the saved theme.
    const frame = requestAnimationFrame(() => document.documentElement.classList.add('theme-ready'))
    return () => cancelAnimationFrame(frame)
  }, [])

  function choose(next: Theme) {
    writeStoredTheme(next)
    setStored(next)
  }

  return { theme, choose }
}
