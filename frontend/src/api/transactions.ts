import { apiDelete, apiGet, apiPost } from './client'

export type AssetType = 'stock' | 'crypto'
export type Side = 'buy' | 'sell'

// Decimal fields travel as strings in both directions so no value ever passes through a JS float.
export interface Transaction {
  id: string
  symbol: string
  asset_type: AssetType
  side: Side
  quantity: string
  price: string
  fee: string
  currency: string
  executed_at: string
  created_at: string
}

export interface TransactionInput {
  symbol: string
  asset_type: AssetType
  side: Side
  quantity: string
  price: string
  fee: string
  executed_at: string
}

export function listTransactions(): Promise<Transaction[]> {
  return apiGet<Transaction[]>('/transactions')
}

export function createTransaction(input: TransactionInput): Promise<Transaction> {
  return apiPost<Transaction>('/transactions', input)
}

export function deleteTransaction(id: string): Promise<void> {
  return apiDelete(`/transactions/${id}`)
}
