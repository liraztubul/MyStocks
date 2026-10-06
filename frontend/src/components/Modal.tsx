import { useEffect, useRef, type ReactNode, type RefObject } from 'react'

interface Props {
  labelledBy: string
  describedBy?: string
  className?: string
  // Focused on open instead of the browser's pick (the first focusable element).
  initialFocus?: RefObject<HTMLElement | null>
  // Where focus goes on close when the opener no longer exists (e.g. its row was removed).
  fallbackFocus?: RefObject<HTMLElement | null>
  // While true, Esc does nothing (a request is in flight).
  busy?: boolean
  onCancel: () => void
  children: ReactNode
}

/** Native <dialog> + showModal(): focus trap, Esc and an inert background come from the browser,
 * with no inline styles or scripts for the CSP to object to. Mounting opens it; unmounting
 * closes it. On phones the CSS turns it into a bottom sheet.
 */
export function Modal({ labelledBy, describedBy, className, initialFocus, fallbackFocus, busy, onCancel, children }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)

  // React unmounts the <dialog> instead of closing it, so the browser never gets to return focus;
  // hand it back to the opener ourselves (like a finally block restoring what we borrowed).
  useEffect(() => {
    const node = dialog.current
    if (!node) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const fallback = fallbackFocus
    node.showModal()
    initialFocus?.current?.focus()
    return () => {
      node.close()
      if (opener?.isConnected) opener.focus()
      else fallback?.current?.focus()
    }
    // Open once per mount; later prop changes must not reopen or refocus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <dialog
      ref={dialog}
      className={`modal card${className ? ` ${className}` : ''}`}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      // Esc fires "cancel"; route it through the same path as the Cancel button.
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onCancel()
      }}
    >
      {children}
    </dialog>
  )
}
