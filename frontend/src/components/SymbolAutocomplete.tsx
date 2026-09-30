import { useId, useState, type KeyboardEvent } from 'react'
import type { AssetMatch } from '../api/assets'
import { useAssetSearch } from '../hooks/useAssets'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

interface Props {
  value: string
  onType: (text: string) => void
  onSelect: (match: AssetMatch) => void
}

export function SymbolAutocomplete({ value, onType, onSelect }: Props) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const query = useDebouncedValue(value, 300)
  const search = useAssetSearch(open ? query : '')
  const results = search.data?.results ?? []
  const showList = open && value.trim() !== '' && results.length > 0

  function choose(match: AssetMatch) {
    onSelect(match)
    setOpen(false)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showList) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((i) => (i + step + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(results[Math.min(active, results.length - 1)])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="autocomplete">
      <input
        required
        maxLength={32}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Search stocks & crypto"
        value={value}
        onChange={(e) => {
          onType(e.target.value)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={handleKeyDown}
      />
      {showList && (
        <ul id={listId} role="listbox" className="autocomplete-list">
          {results.map((match, i) => (
            <li
              key={`${match.asset_type}:${match.provider_id}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : undefined}
              // Keeps focus in the input so its blur doesn't unmount the list before the click lands.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(match)}
            >
              <strong>{match.symbol}</strong> <span className="muted">{match.name}</span>
              <span className={`tag tag-${match.asset_type}`}>{match.asset_type}</span>
            </li>
          ))}
        </ul>
      )}
      {open && search.error && (
        <p className="hint">Search unavailable ({search.error.message}). Type the symbol and pick its type.</p>
      )}
      {open &&
        search.data?.unavailable.map((source) => (
          <p key={source.asset_type} className="hint">
            {source.asset_type === 'stock' ? 'Stock' : 'Crypto'} search unavailable: {source.detail}
          </p>
        ))}
    </div>
  )
}
