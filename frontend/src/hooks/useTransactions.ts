import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createTransaction, deleteTransaction, listTransactions } from '../api/transactions'
import { isSessionExpired } from '../api/writeErrors'
import { useExpireSession } from './useAuth'
import { PORTFOLIO_KEY } from './usePortfolio'

const TRANSACTIONS_KEY = ['transactions']

export function useTransactions() {
  return useQuery({ queryKey: TRANSACTIONS_KEY, queryFn: listTransactions })
}

// Any ledger change moves holdings and P/L, so both views refresh together.
function useInvalidateLedger() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: TRANSACTIONS_KEY }),
      queryClient.invalidateQueries({ queryKey: PORTFOLIO_KEY }),
    ])
}

function useExpireOn401() {
  const expire = useExpireSession()
  return (error: Error) => {
    if (isSessionExpired(error)) expire()
  }
}

export function useCreateTransaction() {
  const invalidate = useInvalidateLedger()
  const onError = useExpireOn401()
  return useMutation({ mutationFn: createTransaction, onSuccess: invalidate, onError })
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateLedger()
  const onError = useExpireOn401()
  return useMutation({ mutationFn: deleteTransaction, onSuccess: invalidate, onError })
}
