import { useRef, useState, type FormEvent, type RefObject } from 'react'
import type { Split } from '../api/splits'
import { writeErrorMessage } from '../api/writeErrors'
import { useDeleteSplit, useUpdateSplit } from '../hooks/useSplits'
import { t } from '../strings'
import { formatDay } from './format'
import { FormError } from './FormError'
import { Icon } from './Icon'
import { Modal } from './Modal'
import { RatioFields, SplitDateField } from './SplitForm'
import { formatRatio } from './splits'

interface Props {
  split: Split
  mode: 'edit' | 'delete'
  onClose: () => void
  fallbackFocus: RefObject<HTMLElement | null>
}

// What the split does today, so an edit or a delete is made knowing what it changes.
function Effect({ split }: { split: Split }) {
  return (
    <p className="confirm-summary">
      <bdi dir="ltr">{formatRatio(split)}</bdi>{' '}
      {t.splits.effect(split.shares_before, split.symbol, formatDay(split.effective_date), split.shares_after)}
    </p>
  )
}

/** Edit or delete a recorded split. The server re-checks the whole ledger either way (a later
 * sell may rely on the split) and says what to fix if it can't apply the change. */
export function SplitDialog({ split, mode, onClose, fallbackFocus }: Props) {
  const safeButton = useRef<HTMLButtonElement>(null)
  const update = useUpdateSplit()
  const remove = useDeleteSplit()
  const [date, setDate] = useState(split.effective_date)
  const [oldShares, setOld] = useState(split.denominator)
  const [newShares, setNew] = useState(split.numerator)
  const pending = update.isPending || remove.isPending
  const error = update.error ?? remove.error

  function save(event: FormEvent) {
    event.preventDefault()
    update.mutate(
      { id: split.id, changes: { effective_date: date, numerator: newShares, denominator: oldShares } },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      labelledBy="split-dialog-title"
      describedBy="split-dialog-body"
      className="confirm-dialog"
      initialFocus={mode === 'delete' ? safeButton : undefined}
      fallbackFocus={fallbackFocus}
      busy={pending}
      onCancel={onClose}
    >
      <div className="confirm-icon" aria-hidden="true">
        <Icon name={mode === 'delete' ? 'trash' : 'edit'} size={22} />
      </div>
      <h2 id="split-dialog-title">
        {mode === 'delete' ? t.splits.deleteTitle : t.splits.editTitle(split.symbol)}
      </h2>
      <form onSubmit={save}>
        <div id="split-dialog-body" className="confirm-body">
          <Effect split={split} />
          {mode === 'delete' ? (
            <p>{t.splits.deleteBody(split.symbol)}</p>
          ) : (
            <div className="stack">
              <SplitDateField value={date} onChange={setDate} />
              <RatioFields oldShares={oldShares} newShares={newShares} onOld={setOld} onNew={setNew} />
            </div>
          )}
          {error && <FormError>{writeErrorMessage(error)}</FormError>}
        </div>
        <div className="modal-actions">
          <button ref={safeButton} type="button" className="button button-secondary" disabled={pending} onClick={onClose}>
            {t.splits.cancel}
          </button>
          {mode === 'delete' ? (
            <button
              type="button"
              className="button button-danger"
              disabled={pending}
              onClick={() => remove.mutate(split.id, { onSuccess: onClose })}
            >
              <Icon name="trash" size={18} />
              {remove.isPending ? t.splits.deleting : t.splits.deleteConfirm}
            </button>
          ) : (
            <button type="submit" className="button button-primary" disabled={pending}>
              {update.isPending ? t.splits.saving : t.splits.save}
            </button>
          )}
        </div>
      </form>
    </Modal>
  )
}
