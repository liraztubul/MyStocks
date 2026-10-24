import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createSplit, deleteSplit, listSplits, updateSplit, type SplitChanges } from '../api/splits'
import { PORTFOLIO_KEY } from './usePortfolio'

export const SPLITS_KEY = ['splits']

export function useSplits(symbol?: string) {
  return useQuery({ queryKey: [...SPLITS_KEY, symbol ?? null], queryFn: () => listSplits(symbol) })
}

// A split converts holdings and average cost, so the portfolio refreshes with the list.
function useInvalidateSplits() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: SPLITS_KEY }),
      queryClient.invalidateQueries({ queryKey: PORTFOLIO_KEY }),
    ])
}

export function useCreateSplit() {
  const invalidate = useInvalidateSplits()
  return useMutation({ mutationFn: createSplit, onSuccess: invalidate })
}

export function useUpdateSplit() {
  const invalidate = useInvalidateSplits()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: SplitChanges }) => updateSplit(id, changes),
    onSuccess: invalidate,
  })
}

export function useDeleteSplit() {
  const invalidate = useInvalidateSplits()
  return useMutation({ mutationFn: deleteSplit, onSuccess: invalidate })
}
