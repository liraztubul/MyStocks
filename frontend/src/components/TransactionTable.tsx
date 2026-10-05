import type { Transaction } from '../api/transactions'
import { useDeleteTransaction } from '../hooks/useTransactions'
import { t } from '../strings'
import { formatDateTime } from './format'
import { Icon } from './Icon'

export function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  const remove = useDeleteTransaction()

  if (transactions.length === 0) return <p className="muted">{t.transactions.empty}</p>

  return (
    <>
      {remove.error && (
        <p role="alert" className="form-error">
          {remove.error.message}
        </p>
      )}
      <div className="table-scroll">
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
                <td className="tabular">{formatDateTime(tx.executed_at)}</td>
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
                    disabled={remove.isPending}
                    aria-label={t.transactions.deleteLabel(tx.symbol, formatDateTime(tx.executed_at))}
                    onClick={() => remove.mutate(tx.id)}
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
    </>
  )
}
