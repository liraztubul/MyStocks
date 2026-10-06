import { type RefObject, useEffect, useRef, useState } from 'react'
import type { Transaction } from '../api/transactions'
import { t } from '../strings'
import { formatDateTime } from './format'
import { Icon } from './Icon'

interface Props {
  transaction: Transaction
  // True when deleting this buy could leave later sells of the same symbol uncovered.
  hasLaterSells: boolean
  pending: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
  // Where focus goes on close when the opener is gone (its row was just deleted).
  fallbackFocus: RefObject<HTMLElement | null>
}

/** Two-step delete confirmation (error prevention: a deletion can't be undone).
 *
 * Native <dialog> + showModal() gives a focus trap, Esc-to-cancel and an inert background for
 * free. In both steps the safe button comes first and takes focus, so a stray Enter cancels.
 */
export function ConfirmDeleteDialog({ transaction: tx, hasLaterSells, pending, error, onCancel, onConfirm, fallbackFocus }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const safeButton = useRef<HTMLButtonElement>(null)
  const [step, setStep] = useState<1 | 2>(1)
  const copy = t.transactions.confirmDelete

  // React unmounts the <dialog> instead of closing it, so the browser never gets to return focus;
  // hand it back to the opener ourselves, or to the table if the opener's row was deleted.
  useEffect(() => {
    const node = dialog.current
    if (!node) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const fallback = fallbackFocus.current
    node.showModal()
    return () => {
      node.close()
      if (opener?.isConnected) opener.focus()
      else fallback?.focus()
    }
  }, [fallbackFocus])

  // Each step starts on its safe button, never on the destructive one.
  useEffect(() => {
    safeButton.current?.focus()
  }, [step])

  return (
    <dialog
      ref={dialog}
      className="confirm-dialog card"
      aria-labelledby="confirm-delete-title"
      aria-describedby="confirm-delete-body"
      // Esc fires "cancel"; route it through the same path as the Cancel button.
      onCancel={(event) => {
        event.preventDefault()
        if (!pending) onCancel()
      }}
    >
      <div className="confirm-icon" aria-hidden="true">
        <Icon name={step === 1 ? 'trash' : 'alert'} size={22} />
      </div>
      <p className="confirm-step">{copy.step(step, 2)}</p>
      <h2 id="confirm-delete-title">{step === 1 ? copy.title : copy.confirmTitle}</h2>
      <div id="confirm-delete-body" className="confirm-body">
        <p className="confirm-summary">
          {copy.summary(
            t.transactions.sides[tx.side],
            tx.quantity,
            tx.symbol,
            tx.price,
            tx.currency,
            formatDateTime(tx.executed_at),
          )}
        </p>
        {step === 2 && <p>{copy.confirmBody}</p>}
        {step === 2 && hasLaterSells && (
          <p className="confirm-warning" role="note">
            <Icon name="alert" size={16} /> {copy.laterSellsWarning(tx.symbol)}
          </p>
        )}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
      </div>
      <div className="confirm-actions">
        {step === 1 ? (
          <>
            <button ref={safeButton} type="button" className="button button-secondary" onClick={onCancel}>
              {copy.cancel}
            </button>
            <button type="button" className="button button-danger-outline" onClick={() => setStep(2)}>
              <Icon name="trash" size={18} />
              {copy.continue}
            </button>
          </>
        ) : (
          <>
            <button
              ref={safeButton}
              type="button"
              className="button button-secondary"
              disabled={pending}
              onClick={onCancel}
            >
              {copy.keep}
            </button>
            <button type="button" className="button button-danger" disabled={pending} onClick={onConfirm}>
              <Icon name="trash" size={18} />
              {pending ? copy.deleting : copy.confirm}
            </button>
          </>
        )}
      </div>
    </dialog>
  )
}
