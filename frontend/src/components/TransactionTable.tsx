import { useRef, useState } from 'react'
import type { Transaction } from '../api/transactions'
import { useDeleteTransaction } from '../hooks/useTransactions'
import { t } from '../strings'
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog'
import { formatDateTime } from './format'
import { Icon } from './Icon'

// Deleting a buy can leave later sells of the same symbol uncovered (the ledger isn't
// re-validated on delete), so the confirmation warns about it up front.
function hasLaterSells(transactions: Transaction[], tx: Transaction): boolean {
  if (tx.side !== 'buy') return false
  const at = new Date(tx.executed_at).getTime()
  return transactions.some(
    (other) => other.symbol === tx.symbol && other.side === 'sell' && new Date(other.executed_at).getTime() >= at,
  )
}

export function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  const remove = useDeleteTransaction()
  const [confirming, setConfirming] = useState<Transaction | null>(null)
  const tableRegion = useRef<HTMLDivElement>(null)

  function close() {
    setConfirming(null)
    remove.reset()
  }

  if (transactions.length === 0) return <p className="muted">{t.transactions.empty}</p>

  return (
    <>
      <div ref={tableRegion} className="table-scroll" tabIndex={-1}>
        <table className="data-table sticky-first">
          <thead>
            <tr>
              <th scope="col">{t.transactions.symbol}</th>
              <th scope="col">{t.transactions.executed}</th>
              <th scope="col">{t.transactions.type}</th>
              <th scope="col">{t.transactions.side}</th>
              <th scope="col" className="num">{t.transactions.quantity}</th>
              <th scope="col" className="num">{t.transactions.price}</th>
              <th scope="col" className="num">{t.transactions.fee}</th>
              <th scope="col">
                <span className="visually-hidden">{t.transactions.actions}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <th scope="row">
                  <span className="symbol">{tx.symbol}</span>
                </th>
                <td className="tabular date-cell">{formatDateTime(tx.executed_at)}</td>
                <td>
                  <span className={`tag tag-${tx.asset_type}`}>{t.transactions.assetTypes[tx.asset_type]}</span>
                </td>
                <td>
                  <span className={`side side-${tx.side}`}>{t.transactions.sides[tx.side]}</span>
                </td>
                <td className="num">{tx.quantity}</td>
                <td className="num">
                  {tx.price} {tx.currency}
                </td>
                <td className="num">{tx.fee}</td>
                <td>
                  <button
                    type="button"
                    className="button button-danger-ghost"
                    aria-label={t.transactions.deleteLabel(tx.symbol, formatDateTime(tx.executed_at))}
                    aria-haspopup="dialog"
                    onClick={() => setConfirming(tx)}
                  >
                    <Icon name="trash" size={18} />
                    <span className="button-text">{t.transactions.delete}</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {confirming && (
        <ConfirmDeleteDialog
          key={confirming.id}
          transaction={confirming}
          hasLaterSells={hasLaterSells(transactions, confirming)}
          pending={remove.isPending}
          error={remove.error?.message ?? null}
          onCancel={close}
          onConfirm={() => remove.mutate(confirming.id, { onSuccess: close })}
          fallbackFocus={tableRegion}
        />
      )}
    </>
  )
}
