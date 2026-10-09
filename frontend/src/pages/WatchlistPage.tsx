import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError, type ErrorCandidate } from '../api/client'
import type { WatchlistItem } from '../api/watchlist'
import { isNotAvailableOnDeployment, writeErrorMessage } from '../api/writeErrors'
import { assetPath } from '../components/assetLinks'
import { CoinCombobox, type CoinComboboxHandle } from '../components/CoinCombobox'
import { CoinPicker } from '../components/CoinPicker'
import { formatQuotePrice, formatRelative, formatSignedPercent } from '../components/format'
import { FormError } from '../components/FormError'
import { Icon } from '../components/Icon'
import { PageHeading } from '../components/PageHeading'
import { Trend } from '../components/Trend'
import { useNow } from '../hooks/useNow'
import { useAddToWatchlist, useRemoveFromWatchlist, useWatchlist } from '../hooks/useWatchlist'
import { t } from '../strings'

// The server's cap (app.services.watchlist.MAX_ITEMS).
const MAX_ITEMS = 50

export default function WatchlistPage() {
  const watchlist = useWatchlist()
  const [announcement, setAnnouncement] = useState('')
  const listHeading = useRef<HTMLHeadingElement>(null)

  return (
    <>
      <PageHeading title={t.watchlist.title} />
      <p className="visually-hidden" role="status">
        {announcement}
      </p>
      <section aria-labelledby="watch-add-heading" className="card section">
        <h2 id="watch-add-heading">{t.watchlist.addHeading}</h2>
        <AddForm items={watchlist.data} onAnnounce={setAnnouncement} />
      </section>
      <section aria-labelledby="watch-list-heading" className="card section">
        <div className="watch-head">
          <h2 id="watch-list-heading" ref={listHeading} tabIndex={-1}>
            {t.watchlist.listHeading}
          </h2>
          {watchlist.data && watchlist.data.length > 0 && (
            <span className="muted watch-count">{t.watchlist.count(watchlist.data.length, MAX_ITEMS)}</span>
          )}
        </div>
        <ListBody
          watchlist={watchlist}
          onRemoved={(symbol) => {
            setAnnouncement(t.watchlist.removed(symbol))
            // The focused button leaves with its row; carry on from the list's heading.
            listHeading.current?.focus()
          }}
        />
      </section>
    </>
  )
}

function ListBody({
  watchlist,
  onRemoved,
}: {
  watchlist: ReturnType<typeof useWatchlist>
  onRemoved: (symbol: string) => void
}) {
  const { data, error, isPending, refetch, isFetching } = watchlist
  const now = useNow(30_000)

  if (isPending) return <ListSkeleton />
  if (!data) {
    return (
      <div className="stack">
        <FormError>
          {t.watchlist.loadFailed} {error?.message}
        </FormError>
        <button type="button" className="button button-secondary page-action" onClick={() => refetch()} disabled={isFetching}>
          {t.watchlist.retry}
        </button>
      </div>
    )
  }
  if (data.length === 0) return <p className="muted">{t.watchlist.empty}</p>

  return (
    <>
      <ul className="watch-list">
        {data.map((item) => (
          <WatchRow key={item.symbol} item={item} now={now} onRemoved={onRemoved} />
        ))}
      </ul>
      <p className="hint attribution">
        {t.watchlist.changeNote}{' '}
        <a href={t.attribution.coingeckoUrl} rel="noreferrer" referrerPolicy="no-referrer">
          {t.attribution.coingecko}
        </a>
      </p>
    </>
  )
}

// Rows of the same shape as the real ones, so the list doesn't jump when they arrive.
function ListSkeleton() {
  return (
    <div aria-busy="true">
      <span className="visually-hidden">{t.common.loading}</span>
      <ul className="watch-list" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <li key={i} className="watch-row">
            <span className="watch-id skeleton skeleton-line" />
            <span className="watch-price skeleton skeleton-line" />
            <span className="watch-remove skeleton skeleton-button" />
          </li>
        ))}
      </ul>
    </div>
  )
}

function unavailableText(item: WatchlistItem): string {
  const known = item.unavailable_code ? t.watchlist.unavailable[item.unavailable_code] : undefined
  return known ?? item.unavailable_reason ?? t.watchlist.unavailableOther
}

function WatchRow({
  item,
  now,
  onRemoved,
}: {
  item: WatchlistItem
  now: number
  onRemoved: (symbol: string) => void
}) {
  const remove = useRemoveFromWatchlist()

  return (
    <li className="watch-row">
      <div className="watch-id">
        <Link className="symbol-link symbol" to={assetPath(item.symbol, item.asset_type, item.coin_id)}>
          {item.symbol}
        </Link>
        {item.coin_id && (
          <span className="watch-coin muted">
            {item.coin_auto_picked ? t.watchlist.autoPicked(item.coin_id) : item.coin_id}
          </span>
        )}
      </div>
      {item.price === null ? (
        <p className="watch-unavailable">
          <Icon name="alert" size={16} className="notice-icon" />
          <span>{unavailableText(item)}</span>
        </p>
      ) : (
        <>
          <div className="watch-price tabular">
            <span className="visually-hidden">{t.watchlist.price}: </span>
            <bdi>{formatQuotePrice(item.price)}</bdi> <span className="unit">{item.currency}</span>
          </div>
          <div className="watch-change">
            <span className="watch-label" aria-hidden="true">
              {t.watchlist.change}
            </span>
            <span className="visually-hidden">{t.watchlist.changeLabel}: </span>
            {item.change_pct === null ? (
              <span className="muted">{t.common.noValue}</span>
            ) : (
              <bdi>
                <Trend value={item.change_pct} text={formatSignedPercent(item.change_pct)} />
              </bdi>
            )}
          </div>
          <div className="watch-updated hint">
            {item.stale && (
              <span className="tag tag-stale">
                <Icon name="clock" size={12} />
                {t.watchlist.stale}
                <span className="visually-hidden">: {t.watchlist.staleDetail}</span>
              </span>
            )}
            {item.price_as_of && <span>{t.watchlist.updated(formatRelative(item.price_as_of, now))}</span>}
          </div>
        </>
      )}
      <div className="watch-remove">
        <button
          type="button"
          className="button button-danger-ghost"
          aria-label={t.watchlist.removeLabel(item.symbol)}
          disabled={remove.isPending}
          onClick={() => remove.mutate(item.symbol, { onSuccess: () => onRemoved(item.symbol) })}
        >
          <Icon name="trash" size={18} />
          {t.watchlist.remove}
        </button>
        {remove.error && <FormError>{writeErrorMessage(remove.error)}</FormError>}
      </div>
    </li>
  )
}

function addErrorMessage(error: Error, symbol: string): string {
  if (!(error instanceof ApiError)) return writeErrorMessage(error)
  if (isNotAvailableOnDeployment(error)) return t.stockData.notAvailable
  switch (error.code) {
    case 'watchlist_full':
      return t.watchlist.errors.full(MAX_ITEMS)
    case 'provider_unavailable':
      return t.watchlist.errors.providerUnavailable(symbol)
    case 'rate_limited':
      return t.watchlist.errors.rateLimited
    case 'symbol_not_found':
      return t.watchlist.errors.notFound(symbol)
    case 'asset_identity_conflict':
      return t.watchlist.errors.conflict(error.message)
    case 'watchlist_crypto_only':
      return t.watchlist.errors.cryptoOnly
    default:
      return writeErrorMessage(error)
  }
}

function AddForm({
  items,
  onAnnounce,
}: {
  items: WatchlistItem[] | undefined
  onAnnounce: (message: string) => void
}) {
  const add = useAddToWatchlist()
  const [symbol, setSymbol] = useState('')
  // Set when several coins share the ticker: the coins to pick from, for that ticker.
  const [choice, setChoice] = useState<{ symbol: string; candidates: ErrorCandidate[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const combo = useRef<CoinComboboxHandle>(null)
  // One add at a time: a second tap or Enter while one is being resolved or saved is ignored
  // (isPending alone updates a render too late for a fast double tap).
  const busy = useRef(false)

  function submit(wanted: string, id?: string) {
    if (busy.current) return
    busy.current = true
    setError(null)
    const already = items?.some((i) => i.symbol === wanted) ?? false
    add.mutate(
      { symbol: wanted, id },
      {
        onSettled: () => {
          busy.current = false
        },
        onSuccess: () => {
          setChoice(null)
          setSymbol('')
          onAnnounce(already ? t.watchlist.alreadyWatched(wanted) : t.watchlist.added(wanted))
          input.current?.focus()
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'ambiguous_symbol') {
            setChoice({ symbol: wanted, candidates: err.candidates ?? [] })
            return
          }
          setChoice(null)
          setError(addErrorMessage(err, wanted))
        },
      },
    )
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const typed = symbol.trim()
    if (!typed || busy.current) return
    busy.current = true
    const coin = (await combo.current?.resolveExact()) ?? null
    busy.current = false
    if (coin) {
      setSymbol(coin.symbol)
      submit(coin.symbol, coin.provider_id)
    } else {
      submit(typed.toUpperCase())
    }
  }

  return (
    <div className="stack">
      <form className="watch-form" onSubmit={onSubmit}>
        <CoinCombobox
          id="watch-symbol"
          label={t.watchlist.symbolLabel}
          placeholder={t.watchlist.symbolPlaceholder}
          hint={t.watchlist.cryptoOnly}
          inputRef={input}
          handle={combo}
          value={symbol}
          onChange={(text) => {
            setSymbol(text)
            setChoice(null)
          }}
          onPick={(coin) => {
            setSymbol(coin.symbol)
            submit(coin.symbol, coin.provider_id)
          }}
        />
        <button type="submit" className="button button-primary watch-add" disabled={add.isPending}>
          <Icon name="plus" size={18} />
          {add.isPending ? t.watchlist.adding : t.watchlist.add}
        </button>
      </form>
      {error && <FormError>{error}</FormError>}
      {choice && (
        <div className="watch-picker">
          <CoinPicker
            symbol={choice.symbol}
            candidates={choice.candidates.map((c) => ({ id: c.provider_id, symbol: c.symbol, name: c.name, rank: null }))}
            body={t.watchlist.pickerBody}
            note={t.watchlist.pickerNote(choice.symbol)}
            showRank={false}
            disabled={add.isPending}
            onPick={(id) => submit(choice.symbol, id)}
          />
          <button type="button" className="button button-ghost page-action" onClick={() => setChoice(null)}>
            {t.watchlist.cancelPick}
          </button>
        </div>
      )}
    </div>
  )
}
