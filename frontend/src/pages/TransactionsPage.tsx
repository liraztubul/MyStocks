import { FirstEntryCelebration } from '../components/FirstEntryCelebration'
import { FormError } from '../components/FormError'
import { PageHeading } from '../components/PageHeading'
import { RowsSkeleton } from '../components/Skeleton'
import { TransactionForm } from '../components/TransactionForm'
import { TransactionTable } from '../components/TransactionTable'
import { useTransactions } from '../hooks/useTransactions'
import { t } from '../strings'

export function TransactionsPage() {
  const { data: transactions, error, isPending } = useTransactions()

  return (
    <>
      <PageHeading title={t.nav.transactions} />
      <FirstEntryCelebration count={transactions?.length} />
      <section aria-labelledby="add-heading" className="card section">
        <h2 id="add-heading">{t.transactions.addHeading}</h2>
        <TransactionForm />
      </section>
      <section aria-labelledby="list-heading" className="card section">
        <h2 id="list-heading">{t.transactions.listHeading}</h2>
        {isPending && <RowsSkeleton rows={4} />}
        {error && (
          <FormError>{t.common.loadError(t.transactions.listHeading, error.message)}</FormError>
        )}
        {transactions && <TransactionTable transactions={transactions} />}
      </section>
    </>
  )
}
