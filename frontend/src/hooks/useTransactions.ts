import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createTransaction, deleteTransaction, listTransactions } from '../api/transactions'

const TRANSACTIONS_KEY = ['transactions']

export function useTransactions() {
  return useQuery({ queryKey: TRANSACTIONS_KEY, queryFn: listTransactions })
}

export function useCreateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createTransaction,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TRANSACTIONS_KEY }),
  })
}

export function useDeleteTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteTransaction,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TRANSACTIONS_KEY }),
  })
}
