import Big from 'big.js'
import { useState, type FormEvent } from 'react'
import type { AssetType, Side, Transaction } from '../api/transactions'
import { useCreateTransaction } from '../hooks/useTransactions'

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
  side: 'buy' as Side,
  quantity: '',
  price: '',
  fee: '0',
  executed_at: '',
}

export function TransactionForm({ transactions }: { transactions: Transaction[] }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const create = useCreateTransaction()

  const symbol = form.symbol.trim().toUpperCase()
  const quantityValid = new RegExp(`^${DECIMAL_PATTERN}$`).test(form.quantity)
  const held = heldQuantity(transactions, symbol)
  const oversell = form.side === 'sell' && symbol !== '' && quantityValid && Big(form.quantity).gt(held)

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: (typeof EMPTY_FORM)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (oversell) return
    create.mutate(
      {
        ...form,
        symbol,
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
        <input
          required
          maxLength={32}
          value={form.symbol}
          onChange={(e) => update('symbol', e.target.value)}
        />
      </label>
      <label>
        Type
        <select value={form.asset_type} onChange={(e) => update('asset_type', e.target.value as AssetType)}>
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
          value={form.price}
          onChange={(e) => update('price', e.target.value)}
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
      <label>
        Executed at
        <input
          type="datetime-local"
          required
          value={form.executed_at}
          onChange={(e) => update('executed_at', e.target.value)}
        />
      </label>
      <button type="submit" disabled={create.isPending || oversell}>
        Add transaction
      </button>
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
