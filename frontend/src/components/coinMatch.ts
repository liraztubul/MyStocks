interface Named {
  symbol: string
  name: string
}

// The suggestion that the typed text names exactly (trimmed, any case), for Enter or Add with no
// option chosen; null keeps the typed-ticker flow.
// - Exactly one coin with that ticker: that coin. A ticker beats another coin's identical name,
//   because tickers are what the app keys on.
// - Several coins sharing that ticker: null on purpose, so the server's coin rules decide (an
//   automatic pick with disclosure when one coin clearly dominates, otherwise the picker)
//   instead of a silent guess here.
// - Otherwise, exactly one coin with that name: that coin.
export function exactSuggestion<T extends Named>(text: string, suggestions: readonly T[]): T | null {
  const typed = text.trim().toLowerCase()
  if (!typed) return null
  const byTicker = suggestions.filter((s) => s.symbol.toLowerCase() === typed)
  if (byTicker.length > 0) return byTicker.length === 1 ? byTicker[0] : null
  const byName = suggestions.filter((s) => s.name.toLowerCase() === typed)
  return byName.length === 1 ? byName[0] : null
}
