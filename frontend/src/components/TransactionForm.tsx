import Big from 'big.js'
import { useState, type FormEvent } from 'react'
import type { AssetMatch } from '../api/assets'
import { ApiError } from '../api/client'
import type { AssetType, Side, Transaction } from '../api/transactions'
import { usePriceOn } from '../hooks/useAssets'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useCreateTransaction } from '../hooks/useTransactions'
import { SymbolAutocomplete } from './SymbolAutocomplete'

const DECIMAL_PATTERN = '\\d+(\\.\\d{1,10})?'

// Mirrors the server's final-balance total only; the server's check (which also walks the
// history chronologically) is the one that counts.
function heldQuantity(transactions: Transaction[], symbol: string): Big {
  return transactions
    .filter((t) => t.symbol === symbol)
    .reduce((held, t) => (t.side === 'buy' ? held.plus(t.quantity) : held.minus(t.quantity)), Big(0))
}

const EMPTY_FORM = {
  symbol: '',
  asset_type: 'stock' as AssetType,
  // Set when the symbol came from search; null when typed by hand.
  provider_id: null as string | null,
  side: 'buy' as Side,
  quantity: '',
  // null means "not typed by the user", so the looked-up price shows through.
  price: null as string | null,
  fee: '0',
  executed_at: '',
}

type FormState = typeof EMPTY_FORM

export function TransactionForm({ transactions }: { transactions: Transaction[] }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const create = useCreateTransaction()

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

  const quantityValid = new RegExp(`^${DECIMAL_PATTERN}$`).test(form.quantity)
  const held = heldQuantity(transactions, symbol)
  const oversell = form.side === 'sell' && symbol !== '' && quantityValid && Big(form.quantity).gt(held)

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
    if (oversell) return
    create.mutate(
      {
        symbol,
        asset_type: form.asset_type,
        side: form.side,
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
    <form onSubmit={handleSubmit} className="transaction-form">
      <label>
        Symbol
        <SymbolAutocomplete
          value={form.symbol}
          onType={(text) => setForm((prev) => ({ ...prev, symbol: text, provider_id: null }))}
          onSelect={selectAsset}
        />
      </label>
      <label>
        Type
        <select
          value={form.asset_type}
          onChange={(e) =>
            setForm((prev) => ({ ...prev, asset_type: e.target.value as AssetType, provider_id: null }))
          }
        >
          <option value="stock">Stock</option>
          <option value="crypto">Crypto</option>
        </select>
      </label>
      <label>
        Side
        <select value={form.side} onChange={(e) => update('side', e.target.value as Side)}>
          <option value="buy">Buy</option>
          <option value="sell">Sell</option>
        </select>
      </label>
      <label>
        Executed at
        <input
          type="datetime-local"
          required
          value={form.executed_at}
          onChange={(e) => update('executed_at', e.target.value)}
        />
      </label>
      <label>
        Quantity
        <input
          required
          inputMode="decimal"
          pattern={DECIMAL_PATTERN}
          value={form.quantity}
          onChange={(e) => update('quantity', e.target.value)}
        />
      </label>
      <label>
        Price (USD)
        <input
          required
          inputMode="decimal"
          pattern={DECIMAL_PATTERN}
          value={price}
          // Clearing the field hands it back to the auto-filled price.
          onChange={(e) => update('price', e.target.value === '' ? null : e.target.value)}
        />
      </label>
      <label>
        Fee (USD)
        <input
          required
          inputMode="decimal"
          pattern={DECIMAL_PATTERN}
          value={form.fee}
          onChange={(e) => update('fee', e.target.value)}
        />
      </label>
      <button type="submit" disabled={create.isPending || oversell}>
        Add transaction
      </button>
      <PriceHint priceOn={priceOn} usingAutoPrice={usingAutoPrice} />
      {oversell && (
        <p role="alert" className="form-message">
          You only hold {held.toString()} {symbol}.
        </p>
      )}
      {create.error && (
        <p role="alert" className="form-message">
          {create.error.message}
        </p>
      )}
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
    return <p className="form-message hint">Looking up price…</p>
  }
  if (priceOn.error) {
    // 404s (no data for that date) already say what to do; outages need the manual-entry nudge.
    const outage = !(priceOn.error instanceof ApiError) || priceOn.error.status >= 500
    return (
      <p role="status" className="form-message hint warning">
        Couldn't auto-fill the price: {priceOn.error.message}
        {outage && ' Enter the price manually.'}
      </p>
    )
  }
  if (!priceOn.data) return null
  const { price, price_date, kind, note, is_fallback } = priceOn.data
  const source = kind === 'live' ? 'live price' : `${price_date} close`
  return (
    <p role="status" className={`form-message hint${is_fallback ? ' warning' : ''}`}>
      {usingAutoPrice ? `Auto-filled ${price} USD (${source}).` : `Looked-up price: ${price} USD (${source}).`}{' '}
      {note}
    </p>
  )
}
