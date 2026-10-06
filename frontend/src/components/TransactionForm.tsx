import { useId, useState, type FormEvent } from 'react'
import type { AssetMatch } from '../api/assets'
import { ApiError } from '../api/client'
import type { AssetType } from '../api/transactions'
import { isNotAvailableOnDeployment, writeErrorMessage } from '../api/writeErrors'
import { usePriceOn } from '../hooks/useAssets'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useCreateTransaction } from '../hooks/useTransactions'
import { t } from '../strings'
import { DECIMAL_PATTERN } from './decimal'
import { FormError } from './FormError'
import { Icon } from './Icon'
import { SymbolAutocomplete } from './SymbolAutocomplete'

const EMPTY_FORM = {
  symbol: '',
  asset_type: 'stock' as AssetType,
  // Set when the symbol came from search; null when typed by hand.
  provider_id: null as string | null,
  quantity: '',
  // null means "not typed by the user", so the looked-up price shows through.
  price: null as string | null,
  fee: '0',
  executed_at: '',
}

type FormState = typeof EMPTY_FORM

// Buys only: selling starts from a holding (SellDialog), where what you hold is already known.
export function TransactionForm() {
  const [form, setForm] = useState(EMPTY_FORM)
  const create = useCreateTransaction()
  const helpId = useId()

  const symbol = form.symbol.trim().toUpperCase()
  const lookupSymbol = useDebouncedValue(symbol, 400)
  // datetime-local is "YYYY-MM-DDTHH:mm" in the browser's zone; its date part is the trade date.
  const tradeDate = form.executed_at.slice(0, 10)
  const priceOn = usePriceOn(
    lookupSymbol && tradeDate
      ? { symbol: lookupSymbol, assetType: form.asset_type, date: tradeDate, providerId: form.provider_id }
      : null,
  )
  const autoPrice = priceOn.data?.price ?? null
  const price = form.price ?? autoPrice ?? ''
  const usingAutoPrice = form.price === null && autoPrice !== null

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function selectAsset(match: AssetMatch) {
    setForm((prev) => ({
      ...prev,
      symbol: match.symbol,
      asset_type: match.asset_type,
      provider_id: match.provider_id,
    }))
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        symbol,
        asset_type: form.asset_type,
        side: 'buy',
        quantity: form.quantity,
        price,
        fee: form.fee,
        // datetime-local has no zone; interpret it in the browser's zone and send UTC.
        executed_at: new Date(form.executed_at).toISOString(),
      },
      { onSuccess: () => setForm({ ...EMPTY_FORM, asset_type: form.asset_type }) },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="transaction-form" aria-describedby={helpId}>
      <div id={helpId} className="form-help">
        <p className="hint">{t.form.buyOnly}</p>
        <p className="hint">{t.form.backdateHint}</p>
      </div>
      <div className="form-grid">
        <label className="field field-symbol">
          <span className="field-label">{t.form.symbol}</span>
          <SymbolAutocomplete
            value={form.symbol}
            onType={(text) => setForm((prev) => ({ ...prev, symbol: text, provider_id: null }))}
            onSelect={selectAsset}
          />
        </label>
        <label className="field">
          <span className="field-label">{t.form.type}</span>
          <select
            value={form.asset_type}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, asset_type: e.target.value as AssetType, provider_id: null }))
            }
          >
            <option value="stock">{t.transactions.assetTypes.stock}</option>
            <option value="crypto">{t.transactions.assetTypes.crypto}</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">{t.form.executedAt}</span>
          <input
            type="datetime-local"
            required
            value={form.executed_at}
            onChange={(e) => update('executed_at', e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">{t.form.quantity}</span>
          <input
            required
            inputMode="decimal"
            pattern={DECIMAL_PATTERN}
            className="num"
            value={form.quantity}
            onChange={(e) => update('quantity', e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">{t.form.price}</span>
          <input
            required
            inputMode="decimal"
            pattern={DECIMAL_PATTERN}
            className="num"
            value={price}
            // Clearing the field hands it back to the auto-filled price.
            onChange={(e) => update('price', e.target.value === '' ? null : e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">{t.form.fee}</span>
          <input
            required
            inputMode="decimal"
            pattern={DECIMAL_PATTERN}
            className="num"
            value={form.fee}
            onChange={(e) => update('fee', e.target.value)}
          />
        </label>
      </div>
      <PriceHint priceOn={priceOn} usingAutoPrice={usingAutoPrice} />
      {create.error && <FormError>{writeErrorMessage(create.error)}</FormError>}
      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={create.isPending}>
          <Icon name="plus" size={18} />
          {t.form.submit}
        </button>
      </div>
    </form>
  )
}

function PriceHint({
  priceOn,
  usingAutoPrice,
}: {
  priceOn: ReturnType<typeof usePriceOn>
  usingAutoPrice: boolean
}) {
  if (priceOn.fetchStatus === 'fetching') {
    return <p className="hint">{t.form.lookingUp}</p>
  }
  if (isNotAvailableOnDeployment(priceOn.error)) {
    return (
      <p role="status" className="hint">
        {t.stockData.autofill}
      </p>
    )
  }
  if (priceOn.error) {
    // 404s (no data for that date) already say what to do; outages need the manual-entry nudge.
    const outage = !(priceOn.error instanceof ApiError) || priceOn.error.status >= 500
    return (
      <p role="status" className="hint warning-text">
        {t.form.autofillFailed(priceOn.error.message)}
        {outage && t.form.enterManually}
      </p>
    )
  }
  if (!priceOn.data) return null
  const { price, price_date, kind, note, is_fallback } = priceOn.data
  const source = kind === 'live' ? t.form.livePrice : t.form.closeOn(price_date)
  return (
    <p role="status" className={is_fallback ? 'hint warning-text' : 'hint'}>
      {usingAutoPrice ? t.form.autoFilled(price, source) : t.form.lookedUp(price, source)} {note}
    </p>
  )
}
