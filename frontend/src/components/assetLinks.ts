import type { AssetType } from '../api/transactions'

// The asset page for a symbol: the type says which provider, the coin id (crypto) which coin.
export function assetPath(symbol: string, type: AssetType, coinId?: string | null): string {
  const query = new URLSearchParams({ type })
  if (coinId) query.set('id', coinId)
  return `/assets/${encodeURIComponent(symbol)}?${query}`
}
