import { apiDelete, apiGet, apiPatch, apiPost } from './client'

// A stock split the user recorded: from effective_date (the ex-date) on, every `denominator`
// shares are `numerator` shares. 4:1 is 4/1; a 1:10 reverse split is 1/10.
export interface Split {
  id: string
  symbol: string
  effective_date: string
  numerator: string
  denominator: string
  // The holding at the start of the split's date, and right after the split.
  shares_before: string
  shares_after: string
  created_at: string
}

export interface SplitInput {
  symbol: string
  effective_date: string
  numerator: string
  denominator: string
}

export type SplitChanges = Partial<Omit<SplitInput, 'symbol'>>

export function listSplits(symbol?: string): Promise<Split[]> {
  return apiGet<Split[]>(symbol ? `/splits?symbol=${encodeURIComponent(symbol)}` : '/splits')
}

export function createSplit(input: SplitInput): Promise<Split> {
  return apiPost<Split>('/splits', input)
}

export function updateSplit(id: string, changes: SplitChanges): Promise<Split> {
  return apiPatch<Split>(`/splits/${id}`, changes)
}

export function deleteSplit(id: string): Promise<void> {
  return apiDelete(`/splits/${id}`)
}
