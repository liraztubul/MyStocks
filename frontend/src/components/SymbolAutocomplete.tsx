import { useId, useState, type KeyboardEvent } from 'react'
import type { AssetMatch } from '../api/assets'
import { useAssetSearch } from '../hooks/useAssets'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { t } from '../strings'

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
        placeholder={t.form.symbolPlaceholder}
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
              <span className="symbol">{match.symbol}</span> <span className="muted option-name">{match.name}</span>
              <span className={`tag tag-${match.asset_type}`}>{match.asset_type}</span>
            </li>
          ))}
        </ul>
      )}
      {open && search.error && (
        <p className="hint">{t.form.searchUnavailable(search.error.message)}</p>
      )}
      {open &&
        search.data?.unavailable.map((source) => (
          <p key={source.asset_type} className="hint">
            {t.form.sourceUnavailable(source.asset_type, source.detail)}
          </p>
        ))}
    </div>
  )
}
