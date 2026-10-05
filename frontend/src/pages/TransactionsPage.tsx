import { TransactionForm } from '../components/TransactionForm'
import { TransactionTable } from '../components/TransactionTable'
import { useTransactions } from '../hooks/useTransactions'

export function TransactionsPage() {
  const { data: transactions, error, isPending } = useTransactions()

  return (
    <>
      <h2>Add transaction</h2>
      <TransactionForm transactions={transactions ?? []} />
      <h2>Transactions</h2>
      {isPending && <p>Loading…</p>}
      {error && <p role="alert">Could not load transactions: {error.message}</p>}
      {transactions && <TransactionTable transactions={transactions} />}
    </>
  )
}
