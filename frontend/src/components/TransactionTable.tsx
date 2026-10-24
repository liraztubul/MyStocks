import { useRef, useState } from 'react'
import type { Split } from '../api/splits'
import type { Transaction } from '../api/transactions'
import { writeErrorMessage } from '../api/writeErrors'
import { useDeleteTransaction } from '../hooks/useTransactions'
import { t } from '../strings'
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog'
import { formatDateTime, formatDay } from './format'
import { Icon } from './Icon'
import { SplitDialog } from './SplitDialog'
import { formatRatio, isReverse, ledgerRows } from './splits'

// Deleting a buy can leave later sells of the same symbol uncovered (the ledger isn't
// re-validated on delete), so the confirmation warns about it up front.
function hasLaterSells(transactions: Transaction[], tx: Transaction): boolean {
  if (tx.side !== 'buy') return false
  const at = new Date(tx.executed_at).getTime()
  return transactions.some(
    (other) => other.symbol === tx.symbol && other.side === 'sell' && new Date(other.executed_at).getTime() >= at,
  )
}

export function TransactionTable({ transactions, splits }: { transactions: Transaction[]; splits: Split[] }) {
  const remove = useDeleteTransaction()
  const [confirming, setConfirming] = useState<Transaction | null>(null)
  const [splitAction, setSplitAction] = useState<{ split: Split; mode: 'edit' | 'delete' } | null>(null)
  const tableRegion = useRef<HTMLDivElement>(null)

  function close() {
    setConfirming(null)
    remove.reset()
  }

  if (transactions.length === 0 && splits.length === 0) return <p className="muted">{t.transactions.empty}</p>

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
            {ledgerRows(transactions, splits).map((row) =>
              row.kind === 'split' ? (
                <SplitRow
                  key={row.split.id}
                  split={row.split}
                  onEdit={() => setSplitAction({ split: row.split, mode: 'edit' })}
                  onDelete={() => setSplitAction({ split: row.split, mode: 'delete' })}
                />
              ) : (
                <TradeRow key={row.trade.id} tx={row.trade} onDelete={() => setConfirming(row.trade)} />
              ),
            )}
          </tbody>
        </table>
      </div>
      {confirming && (
        <ConfirmDeleteDialog
          key={confirming.id}
          transaction={confirming}
          hasLaterSells={hasLaterSells(transactions, confirming)}
          pending={remove.isPending}
          error={remove.error ? writeErrorMessage(remove.error) : null}
          onCancel={close}
          onConfirm={() => remove.mutate(confirming.id, { onSuccess: close })}
          fallbackFocus={tableRegion}
        />
      )}
      {splitAction && (
        <SplitDialog
          key={`${splitAction.split.id}-${splitAction.mode}`}
          split={splitAction.split}
          mode={splitAction.mode}
          onClose={() => setSplitAction(null)}
          fallbackFocus={tableRegion}
        />
      )}
    </>
  )
}

function TradeRow({ tx, onDelete }: { tx: Transaction; onDelete: () => void }) {
  return (
              <tr>
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
                    onClick={onDelete}
                  >
                    <Icon name="trash" size={18} />
                    <span className="button-text">{t.transactions.delete}</span>
                  </button>
                </td>
              </tr>
  )
}

// A split has no price or fee; its quantity column shows the ratio, left to right in any
// direction ("4:1" must never read "1:4").
function SplitRow({ split, onEdit, onDelete }: { split: Split; onEdit: () => void; onDelete: () => void }) {
  const day = formatDay(split.effective_date)
  return (
    <tr>
      <th scope="row">
        <span className="symbol">{split.symbol}</span>
      </th>
      <td className="tabular date-cell">{day}</td>
      <td>
        <span className="tag tag-stock">{t.transactions.assetTypes.stock}</span>
      </td>
      <td>
        <span className="side side-split">{t.splits.side}</span>
      </td>
      <td className="num">
        <bdi dir="ltr">{formatRatio(split)}</bdi>
        {isReverse(split) && <span className="sub">{t.splits.reverse}</span>}
      </td>
      <td className="num">{t.splits.none}</td>
      <td className="num">{t.splits.none}</td>
      <td>
        <div className="row-actions">
          <button
            type="button"
            className="button button-ghost row-action"
            aria-label={t.splits.editLabel(split.symbol, day)}
            aria-haspopup="dialog"
            onClick={onEdit}
          >
            <Icon name="edit" size={18} />
            <span className="button-text">{t.splits.edit}</span>
          </button>
          <button
            type="button"
            className="button button-danger-ghost"
            aria-label={t.splits.deleteLabel(split.symbol, day)}
            aria-haspopup="dialog"
            onClick={onDelete}
          >
            <Icon name="trash" size={18} />
            <span className="button-text">{t.transactions.delete}</span>
          </button>
        </div>
      </td>
    </tr>
  )
}
