import Big from 'big.js'
import { useId, useRef, useState, type FormEvent, type RefObject } from 'react'
import type { Holding } from '../api/portfolio'
import type { Transaction } from '../api/transactions'
import { writeErrorMessage } from '../api/writeErrors'
import { useCreateTransaction } from '../hooks/useTransactions'
import { t } from '../strings'
import { DECIMAL_PATTERN, isDecimal } from './decimal'
import { formatDateTime } from './format'
import { FormError } from './FormError'
import { Modal } from './Modal'

// The API's precision. Quick amounts round DOWN to it, so they can never exceed what's held.
const API_DECIMALS = 10

const QUICK_SHARES = [
  { label: t.sell.quarter, share: '0.25' },
  { label: t.sell.half, share: '0.5' },
] as const

function quickAmount(held: string, share: string): string {
  return Big(held).times(share).round(API_DECIMALS, Big.roundDown).toFixed()
}

// datetime-local wants "YYYY-MM-DDTHH:mm" in the browser's zone.
function nowLocal(): string {
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  return now.toISOString().slice(0, 16)
}

function amountError(value: string, { allowZero }: { allowZero: boolean }): string | null {
  if (value === '') return t.sell.required
  if (!isDecimal(value)) return t.sell.badNumber
  if (!allowZero && Big(value).eq(0)) return t.sell.mustBePositive
  return null
}

interface Props {
  // A snapshot taken when the dialog opened: the 60 s price poll must not move numbers under the cursor.
  holding: Holding
  onSold: (sale: Transaction) => void
  onCancel: () => void
  fallbackFocus: RefObject<HTMLElement | null>
}

export function SellDialog({ holding: h, onSold, onCancel, fallbackFocus }: Props) {
  const create = useCreateTransaction()
  const base = useId()
  const id = (part: string) => `${base}-${part}`
  const quantityInput = useRef<HTMLInputElement>(null)
  const priceInput = useRef<HTMLInputElement>(null)
  const feeInput = useRef<HTMLInputElement>(null)
  const whenInput = useRef<HTMLInputElement>(null)

  // Only a fresh market price is a safe default; a stale or missing one must be typed in.
  const marketPrice = h.current_price !== null && !h.price_is_stale ? h.current_price : null
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState(marketPrice ?? '')
  const [fee, setFee] = useState('0')
  const [executedAt, setExecutedAt] = useState(nowLocal)
  const [submitted, setSubmitted] = useState(false)

  const quick = QUICK_SHARES.map((q) => ({ ...q, amount: quickAmount(h.quantity, q.share) }))
  const tooSmall = quick.filter((q) => Big(q.amount).eq(0))

  const quantityFormat = amountError(quantity, { allowZero: false })
  const quantityError = quantityFormat ?? (Big(quantity).gt(h.quantity) ? t.sell.moreThanHeld(h.quantity, h.symbol) : null)
  const priceError = amountError(price, { allowZero: false })
  const feeError = amountError(fee, { allowZero: true })
  const whenError = executedAt === '' ? t.sell.required : null

  // Required-but-empty only nags after a submit attempt; anything typed and wrong shows at once.
  const show = (error: string | null, value: string) => (error && (submitted || value !== '') ? error : null)
  const shown = {
    quantity: show(quantityError, quantity),
    price: show(priceError, price),
    fee: show(feeError, fee),
    when: show(whenError, executedAt),
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    const firstInvalid = [
      [quantityError, quantityInput],
      [priceError, priceInput],
      [feeError, feeInput],
      [whenError, whenInput],
    ].find(([error]) => error) as [string, RefObject<HTMLInputElement | null>] | undefined
    if (firstInvalid) {
      firstInvalid[1].current?.focus()
      return
    }
    // mutateAsync, not mutate + onSuccess: the per-call callback is dropped if this component
    // unmounts first, which is exactly what happens when the last unit is sold.
    create
      .mutateAsync({
        symbol: h.symbol,
        asset_type: h.asset_type,
        side: 'sell',
        quantity,
        price,
        fee,
        // datetime-local has no zone; interpret it in the browser's zone and send UTC.
        executed_at: new Date(executedAt).toISOString(),
      })
      .then(onSold)
      .catch(() => {
        // Shown from create.error below; a 401 already swapped to the login page.
      })
  }

  const priceHint =
    marketPrice !== null && h.price_as_of
      ? t.sell.priceFresh(formatDateTime(h.price_as_of))
      : h.current_price !== null && h.price_as_of
        ? t.sell.priceStale(h.current_price, formatDateTime(h.price_as_of))
        : h.price_unavailable_reason
          ? t.sell.priceUnavailable(h.price_unavailable_reason)
          : t.sell.priceUnavailableNoReason
  const priceNeedsInput = marketPrice === null

  return (
    <Modal
      labelledBy={id('title')}
      describedBy={id('held')}
      className="sell-dialog"
      initialFocus={quantityInput}
      fallbackFocus={fallbackFocus}
      busy={create.isPending}
      onCancel={onCancel}
    >
      <form onSubmit={handleSubmit} noValidate className="sell-form">
        <div className="sell-head">
          <h2 id={id('title')}>
            {t.sell.title(h.symbol)} <span className={`tag tag-${h.asset_type}`}>{t.transactions.assetTypes[h.asset_type]}</span>
          </h2>
          <p id={id('held')} className="sell-held">
            {t.sell.held(h.quantity, h.symbol)}
          </p>
        </div>

        <div className="field">
          <label htmlFor={id('quantity')} className="field-label">
            {t.sell.quantity}
          </label>
          <input
            ref={quantityInput}
            id={id('quantity')}
            inputMode="decimal"
            autoComplete="off"
            pattern={DECIMAL_PATTERN}
            className="num"
            required
            aria-invalid={shown.quantity ? true : undefined}
            aria-describedby={[id('held'), shown.quantity && id('quantity-error'), tooSmall.length > 0 && id('quick-hint')].filter(Boolean).join(' ')}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />
          <div className="quick-amounts" role="group" aria-label={t.sell.quickLabel}>
            {quick.map((q) => (
              <button
                key={q.share}
                type="button"
                className="button button-secondary quick-amount"
                disabled={Big(q.amount).eq(0)}
                aria-describedby={Big(q.amount).eq(0) ? id('quick-hint') : undefined}
                onClick={() => setQuantity(q.amount)}
              >
                {q.label}
              </button>
            ))}
            <button type="button" className="button button-secondary quick-amount" onClick={() => setQuantity(h.quantity)}>
              {t.sell.all}
            </button>
          </div>
          {tooSmall.length > 0 && (
            <p id={id('quick-hint')} className="field-hint">
              {tooSmall.length === QUICK_SHARES.length ? t.sell.tooSmallBoth : t.sell.tooSmall(tooSmall[0].label)}
            </p>
          )}
          {shown.quantity && <FormError quiet id={id('quantity-error')}>{shown.quantity}</FormError>}
        </div>

        <div className="sell-grid">
          <div className="field">
            <label htmlFor={id('price')} className="field-label">
              {t.sell.price}
            </label>
            <input
              ref={priceInput}
              id={id('price')}
              inputMode="decimal"
              autoComplete="off"
              pattern={DECIMAL_PATTERN}
              className="num"
              required
              aria-invalid={shown.price ? true : undefined}
              aria-describedby={`${id('price-hint')}${shown.price ? ` ${id('price-error')}` : ''}`}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
            <p id={id('price-hint')} className={priceNeedsInput ? 'field-hint warning-text' : 'field-hint'}>
              {priceHint}
            </p>
            {shown.price && <FormError quiet id={id('price-error')}>{shown.price}</FormError>}
          </div>
          <div className="field">
            <label htmlFor={id('fee')} className="field-label">
              {t.sell.fee}
            </label>
            <input
              ref={feeInput}
              id={id('fee')}
              inputMode="decimal"
              autoComplete="off"
              pattern={DECIMAL_PATTERN}
              className="num"
              required
              aria-invalid={shown.fee ? true : undefined}
              aria-describedby={shown.fee ? id('fee-error') : undefined}
              value={fee}
              onChange={(e) => setFee(e.target.value)}
            />
            {shown.fee && <FormError quiet id={id('fee-error')}>{shown.fee}</FormError>}
          </div>
          <div className="field sell-when">
            <label htmlFor={id('when')} className="field-label">
              {t.sell.executedAt}
            </label>
            <input
              ref={whenInput}
              id={id('when')}
              type="datetime-local"
              required
              aria-invalid={shown.when ? true : undefined}
              aria-describedby={`${id('when-hint')}${shown.when ? ` ${id('when-error')}` : ''}`}
              value={executedAt}
              onChange={(e) => setExecutedAt(e.target.value)}
            />
            <p id={id('when-hint')} className="field-hint">
              {t.sell.executedAtHint}
            </p>
            {shown.when && <FormError quiet id={id('when-error')}>{shown.when}</FormError>}
          </div>
        </div>

        {create.error && <FormError>{writeErrorMessage(create.error)}</FormError>}

        <div className="modal-actions">
          <button type="button" className="button button-secondary" disabled={create.isPending} onClick={onCancel}>
            {t.sell.cancel}
          </button>
          <button type="submit" className="button button-primary" disabled={create.isPending}>
            {create.isPending ? t.sell.submitting : t.sell.submit}
          </button>
        </div>
      </form>
    </Modal>
  )
}
