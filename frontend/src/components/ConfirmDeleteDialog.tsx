import { useEffect, useRef, useState, type RefObject } from 'react'
import type { Transaction } from '../api/transactions'
import { t } from '../strings'
import { formatDateTime } from './format'
import { FormError } from './FormError'
import { Icon } from './Icon'
import { Modal } from './Modal'

interface Props {
  transaction: Transaction
  // True when deleting this buy could leave later sells of the same symbol uncovered.
  hasLaterSells: boolean
  pending: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
  fallbackFocus: RefObject<HTMLElement | null>
}

/** Two-step delete confirmation (error prevention: a deletion can't be undone). In both steps
 * the safe button comes first and takes focus, so a stray Enter cancels.
 */
export function ConfirmDeleteDialog({ transaction: tx, hasLaterSells, pending, error, onCancel, onConfirm, fallbackFocus }: Props) {
  const safeButton = useRef<HTMLButtonElement>(null)
  const [step, setStep] = useState<1 | 2>(1)
  const copy = t.transactions.confirmDelete

  // Each step starts on its safe button, never on the destructive one.
  useEffect(() => {
    safeButton.current?.focus()
  }, [step])

  return (
    <Modal
      labelledBy="confirm-delete-title"
      describedBy="confirm-delete-body"
      className="confirm-dialog"
      initialFocus={safeButton}
      fallbackFocus={fallbackFocus}
      busy={pending}
      onCancel={onCancel}
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
        {error && <FormError>{error}</FormError>}
      </div>
      <div className="modal-actions">
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
    </Modal>
  )
}
