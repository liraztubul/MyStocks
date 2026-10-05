import { RowsSkeleton } from '../components/Skeleton'
import { TransactionForm } from '../components/TransactionForm'
import { TransactionTable } from '../components/TransactionTable'
import { useTransactions } from '../hooks/useTransactions'
import { t } from '../strings'

export function TransactionsPage() {
  const { data: transactions, error, isPending } = useTransactions()

  return (
    <>
      <section aria-labelledby="add-heading" className="card section">
        <h2 id="add-heading">{t.transactions.addHeading}</h2>
        <TransactionForm transactions={transactions ?? []} />
      </section>
      <section aria-labelledby="list-heading" className="card section">
        <h2 id="list-heading">{t.transactions.listHeading}</h2>
        {isPending && <RowsSkeleton rows={4} />}
        {error && (
          <p role="alert" className="form-error">
            {t.common.loadError(t.transactions.listHeading, error.message)}
          </p>
        )}
        {transactions && <TransactionTable transactions={transactions} />}
      </section>
    </>
  )
}
