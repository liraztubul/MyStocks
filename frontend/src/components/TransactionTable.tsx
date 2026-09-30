import type { Transaction } from '../api/transactions'
import { useDeleteTransaction } from '../hooks/useTransactions'

export function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  const remove = useDeleteTransaction()

  if (transactions.length === 0) return <p>No transactions yet.</p>

  return (
    <>
      {remove.error && <p role="alert">{remove.error.message}</p>}
      <table className="transaction-table">
        <thead>
          <tr>
            <th>Executed</th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Side</th>
            <th className="num">Quantity</th>
            <th className="num">Price</th>
            <th className="num">Fee</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.id}>
              <td>{new Date(t.executed_at).toLocaleString()}</td>
              <td>{t.symbol}</td>
              <td>{t.asset_type}</td>
              <td>{t.side}</td>
              <td className="num">{t.quantity}</td>
              <td className="num">
                {t.price} {t.currency}
              </td>
              <td className="num">{t.fee}</td>
              <td>
                <button
                  type="button"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(t.id)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
