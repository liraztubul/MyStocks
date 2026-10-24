import { useId, useState, type FormEvent } from 'react'
import { writeErrorMessage } from '../api/writeErrors'
import { useCreateSplit } from '../hooks/useSplits'
import { t } from '../strings'
import { DECIMAL_PATTERN } from './decimal'
import { FormError } from './FormError'
import { Icon } from './Icon'
import { newYorkDay } from './splits'

// "Every [old] shares became [new]": the sentence follows the page's direction, so it reads
// naturally in RTL too; each input carries its own label.
export function RatioFields({
  oldShares,
  newShares,
  onOld,
  onNew,
}: {
  oldShares: string
  newShares: string
  onOld: (value: string) => void
  onNew: (value: string) => void
}) {
  const hintId = useId()
  return (
    <fieldset className="field ratio-field" aria-describedby={hintId}>
      <legend className="field-label">{t.splits.ratio}</legend>
      <div className="ratio-row">
        <span>{t.splits.every}</span>
        <input
          required
          inputMode="decimal"
          pattern={DECIMAL_PATTERN}
          className="num ratio-input"
          aria-label={t.splits.oldShares}
          value={oldShares}
          onChange={(e) => onOld(e.target.value)}
        />
        <span>{t.splits.became}</span>
        <input
          required
          inputMode="decimal"
          pattern={DECIMAL_PATTERN}
          className="num ratio-input"
          aria-label={t.splits.newShares}
          value={newShares}
          onChange={(e) => onNew(e.target.value)}
        />
      </div>
      <span id={hintId} className="field-hint">
        {t.splits.ratioHint}
      </span>
    </fieldset>
  )
}

export function SplitDateField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const hintId = useId()
  return (
    <label className="field">
      <span className="field-label">{t.splits.date}</span>
      <input
        type="date"
        required
        // The server refuses a future split: the replay would apply it at once.
        max={newYorkDay(new Date())}
        aria-describedby={hintId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <span id={hintId} className="field-hint">
        {t.splits.dateHint}
      </span>
    </label>
  )
}

const EMPTY = { symbol: '', date: '', oldShares: '1', newShares: '' }

export function SplitForm() {
  const [form, setForm] = useState(EMPTY)
  const create = useCreateSplit()
  const helpId = useId()

  function update<K extends keyof typeof EMPTY>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        symbol: form.symbol.trim().toUpperCase(),
        effective_date: form.date,
        numerator: form.newShares,
        denominator: form.oldShares,
      },
      { onSuccess: () => setForm(EMPTY) },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="transaction-form" aria-describedby={helpId}>
      <p id={helpId} className="hint">
        {t.splits.intro}
      </p>
      <div className="form-grid">
        <label className="field">
          <span className="field-label">{t.splits.symbol}</span>
          <input
            required
            maxLength={32}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            value={form.symbol}
            onChange={(e) => update('symbol', e.target.value)}
          />
        </label>
        <SplitDateField value={form.date} onChange={(value) => update('date', value)} />
        <RatioFields
          oldShares={form.oldShares}
          newShares={form.newShares}
          onOld={(value) => update('oldShares', value)}
          onNew={(value) => update('newShares', value)}
        />
      </div>
      {create.error && <FormError>{writeErrorMessage(create.error)}</FormError>}
      {create.isSuccess && (
        <p role="status" className="hint">
          {t.splits.recordedNotice}
        </p>
      )}
      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={create.isPending}>
          <Icon name="plus" size={18} />
          {t.splits.submit}
        </button>
      </div>
    </form>
  )
}
