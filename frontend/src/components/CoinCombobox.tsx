import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useId, useImperativeHandle, useState, type KeyboardEvent, type Ref } from 'react'
import type { CoinSuggestResponse, CoinSuggestion } from '../api/coins'
import { coinSuggestQuery, MIN_SUGGEST_LENGTH, useCoinSuggest } from '../hooks/useCoinSuggest'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { t } from '../strings'
import { exactSuggestion } from './coinMatch'

interface Props {
  id: string
  label: string
  value: string
  onChange: (text: string) => void
  // A suggestion was chosen: add it by its coin id, no lookup needed.
  onPick: (coin: CoinSuggestion) => void
  hint: string
  placeholder?: string
  inputRef?: Ref<HTMLInputElement>
  handle?: Ref<CoinComboboxHandle>
}

export interface CoinComboboxHandle {
  // For Enter or Add with no option chosen: the suggestion the typed text names exactly (see
  // coinMatch), asked for the current text even if typing hasn't settled; null keeps the
  // typed-ticker flow, also when suggestions are unavailable.
  resolveExact: () => Promise<CoinSuggestion | null>
}

// A WAI-ARIA 1.2 combobox (editable, list autocomplete without automatic selection): focus stays
// in the input and the active option is conveyed with aria-activedescendant. Enter with no
// active option submits the surrounding form as typed, so an exact ticker outside the index
// still works. If suggestions are unavailable it quietly becomes a plain text field.
export function CoinCombobox({ id, label, value, onChange, onPick, hint, placeholder, inputRef, handle }: Props) {
  const listId = useId()
  const hintId = useId()
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const debounced = useDebouncedValue(value, 150)
  const suggest = useCoinSuggest(debounced)
  // The active option belongs to one answer: a new answer starts with none active, so Enter keeps
  // meaning "this exact ticker" until the user arrows into the list.
  const [cursor, setCursor] = useState<{ answer: CoinSuggestResponse | undefined; index: number }>({
    answer: undefined,
    index: -1,
  })
  const active = cursor.answer === suggest.data ? cursor.index : -1
  const setActive = (index: number) => setCursor({ answer: suggest.data, index })

  const query = value.trim()
  const enabled = query.length >= MIN_SUGGEST_LENGTH
  const degraded = enabled && (suggest.isError || (suggest.data?.reason ?? null) !== null)
  const results = enabled && !degraded ? (suggest.data?.results ?? []) : []
  const answered =
    suggest.data !== undefined && !suggest.isPlaceholderData && debounced.trim() === query && !suggest.isFetching
  const showList = open && results.length > 0
  const noMatch = open && enabled && !degraded && answered && results.length === 0

  useEffect(() => {
    if (active >= 0) document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: 'nearest' })
  }, [active, listId])

  useImperativeHandle(
    handle,
    () => ({
      async resolveExact() {
        if (value.trim().length < MIN_SUGGEST_LENGTH) return null
        try {
          const answer = await queryClient.fetchQuery(coinSuggestQuery(value))
          return answer.reason === null ? exactSuggestion(value, answer.results) : null
        } catch {
          return null
        }
      },
    }),
    [value, queryClient],
  )

  function pick(coin: CoinSuggestion) {
    setOpen(false)
    setActive(-1)
    onPick(coin)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    const last = results.length - 1
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp': {
        if (results.length === 0) return
        event.preventDefault()
        const down = event.key === 'ArrowDown'
        if (!showList) {
          setOpen(true)
          setActive(down ? 0 : last)
        } else if (active < 0) {
          setActive(down ? 0 : last)
        } else {
          setActive((active + (down ? 1 : -1) + results.length) % results.length)
        }
        return
      }
      case 'Home':
      case 'End':
        // Only while an option is active; otherwise they move the text cursor as usual.
        if (showList && active >= 0) {
          event.preventDefault()
          setActive(event.key === 'Home' ? 0 : last)
        }
        return
      case 'Enter':
        if (showList && active >= 0) {
          event.preventDefault()
          pick(results[active])
        }
        return
      case 'Escape':
        if (open) {
          event.preventDefault()
          setOpen(false)
          setActive(-1)
        }
        return
    }
  }

  let announcement = ''
  if (degraded && open) announcement = t.coinSuggest.unavailable
  else if (showList && answered) announcement = t.coinSuggest.count(results.length)
  else if (noMatch) announcement = t.coinSuggest.noMatch

  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div className="combobox">
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showList}
          aria-controls={listId}
          aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
          aria-describedby={hintId}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={50}
          placeholder={placeholder}
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            setOpen(false)
            setActive(-1)
          }}
          onKeyDown={onKeyDown}
        />
        <ul id={listId} role="listbox" aria-label={t.coinSuggest.listLabel} className="combobox-list" hidden={!showList}>
          {results.map((coin, i) => (
            <li
              key={coin.provider_id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className="combobox-option"
              // Keeps focus in the input, so its blur doesn't close the list before the click lands.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(coin)}
            >
              <span className="combobox-name">{coin.name}</span>
              <span className="combobox-symbol">{coin.symbol}</span>
              <span className="combobox-rank">
                {coin.market_cap_rank !== null ? t.coinSuggest.rank(coin.market_cap_rank) : t.coinSuggest.unranked}
              </span>
            </li>
          ))}
        </ul>
        {noMatch && <p className="combobox-empty">{t.coinSuggest.noMatch}</p>}
      </div>
      <span id={hintId} className="field-hint">
        {degraded ? t.coinSuggest.unavailable : hint}
      </span>
      <p className="visually-hidden" role="status">
        {announcement}
      </p>
    </div>
  )
}
