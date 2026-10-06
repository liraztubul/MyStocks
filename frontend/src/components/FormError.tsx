import type { ReactNode } from 'react'
import { Icon } from './Icon'

// Errors carry an icon and words as well as the red, so colour is never the only signal.
// Field-level messages pass quiet: they're read through aria-describedby when the field has
// focus, instead of an alert interrupting on every keystroke.
export function FormError({ id, quiet, children }: { id?: string; quiet?: boolean; children: ReactNode }) {
  return (
    <p role={quiet ? undefined : 'alert'} id={id} className="form-error">
      <Icon name="alert" size={16} className="form-error-icon" />
      <span>{children}</span>
    </p>
  )
}
