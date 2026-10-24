import { useState } from 'react'
import { FirstEntryCelebration } from '../components/FirstEntryCelebration'
import { FormError } from '../components/FormError'
import { PageHeading } from '../components/PageHeading'
import { RowsSkeleton } from '../components/Skeleton'
import { SplitForm } from '../components/SplitForm'
import { TransactionForm } from '../components/TransactionForm'
import { TransactionTable } from '../components/TransactionTable'
import { useSplits } from '../hooks/useSplits'
import { useTransactions } from '../hooks/useTransactions'
import { t } from '../strings'

export function TransactionsPage() {
  const { data: transactions, error, isPending } = useTransactions()
  const splits = useSplits()
  const [kind, setKind] = useState<'buy' | 'split'>('buy')

  return (
    <>
      <PageHeading title={t.nav.transactions} />
      <FirstEntryCelebration count={transactions?.length} />
      <section aria-labelledby="add-heading" className="card section">
        <h2 id="add-heading">{kind === 'buy' ? t.transactions.addHeading : t.splits.addHeading}</h2>
        <fieldset className="entry-kind">
          <legend className="visually-hidden">{t.splits.kindLabel}</legend>
          {(['buy', 'split'] as const).map((value) => (
            <label key={value}>
              <input
                type="radio"
                name="entry-kind"
                value={value}
                checked={kind === value}
                onChange={() => setKind(value)}
              />
              <span>{t.splits.kinds[value]}</span>
            </label>
          ))}
        </fieldset>
        {kind === 'buy' ? <TransactionForm /> : <SplitForm />}
      </section>
      <section aria-labelledby="list-heading" className="card section">
        <h2 id="list-heading">{t.transactions.listHeading}</h2>
        {(isPending || splits.isPending) && <RowsSkeleton rows={4} />}
        {error && (
          <FormError>{t.common.loadError(t.transactions.listHeading, error.message)}</FormError>
        )}
        {splits.error && <FormError>{t.common.loadError(t.splits.listName, splits.error.message)}</FormError>}
        {transactions && splits.data && <TransactionTable transactions={transactions} splits={splits.data} />}
      </section>
    </>
  )
}
