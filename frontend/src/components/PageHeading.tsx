import { useEffect, useRef, type ReactNode } from 'react'
import { useLocation } from 'react-router'
import { t } from '../strings'

// Each page's <h1>: names the page for screen readers and the browser tab. After in-app
// navigation it takes focus and the page scrolls to the top, the way a full page load would.
// The very first location has key "default", so a reload or deep link doesn't steal focus.
export function PageHeading({ title, children }: { title: string; children?: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const { key } = useLocation()

  useEffect(() => {
    document.title = `${title} · ${t.appName}`
  }, [title])

  useEffect(() => {
    if (key === 'default') return
    window.scrollTo(0, 0)
    heading.current?.focus()
  }, [key])

  return (
    <h1 ref={heading} tabIndex={-1} className="visually-hidden">
      {children ?? title}
    </h1>
  )
}
