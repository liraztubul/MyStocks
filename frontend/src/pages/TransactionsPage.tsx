import type { User } from '../api/auth'
import { TransactionForm } from '../components/TransactionForm'
import { TransactionTable } from '../components/TransactionTable'
import { useTransactions } from '../hooks/useTransactions'

export function TransactionsPage({ user }: { user: User }) {
  const { data: transactions, error, isPending } = useTransactions()

  return (
    <main className="wide">
      <header className="page-header">
        <h1>MyStocks</h1>
        <span>
          Logged in as <strong data-testid="user-email">{user.email}</strong>
        </span>
      </header>
      <h2>Add transaction</h2>
      <TransactionForm transactions={transactions ?? []} />
      <h2>Transactions</h2>
      {isPending && <p>Loading…</p>}
      {error && <p role="alert">Could not load transactions: {error.message}</p>}
      {transactions && <TransactionTable transactions={transactions} />}
    </main>
  )
}
