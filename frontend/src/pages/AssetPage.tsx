import Big from 'big.js'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ApiError } from '../api/client'
import {
  HISTORY_RANGES,
  type AssetHistory,
  type CoinCandidate,
  type HistoryRange,
  type UndrawnReason,
} from '../api/history'
import type { AssetType } from '../api/transactions'
import { formatDateTime, formatDay, formatPrice } from '../components/format'
import { FormError } from '../components/FormError'
import { Icon } from '../components/Icon'
import { PageHeading } from '../components/PageHeading'
import PriceChart from '../components/PriceChart'
import { useAssetSearch } from '../hooks/useAssets'
import { useAssetHistory } from '../hooks/useAssetHistory'
import { t } from '../strings'

const TRADINGVIEW_URL = 'https://www.tradingview.com/'
const COINGECKO_URL = 'https://www.coingecko.com/en/api'

// One page per asset, held or not (a watched symbol isn't a holding). Lazily loaded with its
// chart library, so other pages don't pay for it.
export default function AssetPage() {
  const symbol = (useParams().symbol ?? '').toUpperCase()
  const [search] = useSearchParams()
  const type = (search.get('type') as AssetType | null) ?? null
  const id = search.get('id')
  const choosing = search.get('choose') === '1'
  const [range, setRange] = useState<HistoryRange>('1Y')
  const history = useAssetHistory({ symbol, range, type, id })

  return (
    <section className="card section asset-page" aria-labelledby="asset-heading">
      <PageHeading title={symbol} />
      <div className="asset-head">
        <h2 id="asset-heading">{symbol}</h2>
        {history.data && (
          <span className={`tag tag-${history.data.asset_type}`}>
            {t.transactions.assetTypes[history.data.asset_type]}
          </span>
        )}
      </div>
      <AssetBody
        symbol={symbol}
        range={range}
        onRange={setRange}
        choosing={choosing}
        history={history}
      />
      <Link className="button button-ghost page-action" to="/">
        {t.holding.backToDashboard}
      </Link>
    </section>
  )
}

function AssetBody({
  symbol,
  range,
  onRange,
  choosing,
  history,
}: {
  symbol: string
  range: HistoryRange
  onRange: (range: HistoryRange) => void
  choosing: boolean
  history: ReturnType<typeof useAssetHistory>
}) {
  const { data, error, isPending, refetch, isFetching } = history

  if (isPending) return <ChartSkeleton />
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="notice notice-info" role="status">
        <Icon name="alert" size={18} className="notice-icon" />
        <div>
          <strong>{t.asset.notFoundTitle(symbol)}</strong> {t.asset.notFoundBody}
        </div>
      </div>
    )
  }
  if (error instanceof ApiError && error.status === 422) return <TypeChooser symbol={symbol} />
  if (error || !data) {
    return (
      <div className="stack">
        <FormError>{t.asset.loadFailed}</FormError>
        <button type="button" className="button button-secondary page-action" onClick={() => refetch()} disabled={isFetching}>
          {t.asset.retry}
        </button>
      </div>
    )
  }

  if (data.ambiguous) {
    return (
      <>
        <CoinPicker symbol={symbol} candidates={data.candidates} body={t.asset.pickerBody} />
        <TradesTable data={data} />
      </>
    )
  }
  if (choosing) {
    return (
      <>
        <SearchPicker symbol={symbol} />
        <TradesTable data={data} />
      </>
    )
  }
  if (!data.available) {
    return (
      <>
        <div className="notice notice-info" role="status">
          <Icon name="alert" size={18} className="notice-icon" />
          <div>
            {data.unavailable_reason === 'not_available_on_deployment'
              ? t.asset.notOnDeployment
              : t.asset.providerNotConfigured}
          </div>
        </div>
        <TradesTable data={data} />
      </>
    )
  }

  return (
    <>
      {data.coin_auto_picked && (
        <p className="hint coin-disclosure">
          {t.asset.autoPicked(data.coin_name ?? data.coin_id ?? symbol)}{' '}
          <Link to={`?type=crypto&choose=1`}>{t.asset.notThisOne}</Link>
        </p>
      )}
      <RangeButtons value={range} onChange={onRange} />
      {data.is_stale && (
        <div className="notice" role="status">
          <Icon name="clock" size={18} className="notice-icon" />
          <div>{data.as_of ? t.asset.stale(formatDateTime(data.as_of)) : t.asset.staleNever}</div>
        </div>
      )}
      {data.range_note && <p className="hint">{data.range_note}</p>}
      {data.bars.length === 0 ? (
        !data.is_stale && <p className="muted">{t.asset.empty(symbol)}</p>
      ) : (
        <ChartFigure data={data} symbol={symbol} />
      )}
      {!data.is_stale && data.as_of && <p className="hint">{t.asset.asOf(formatDateTime(data.as_of))}</p>}
      <p className="hint attribution">
        <a href={TRADINGVIEW_URL} rel="noreferrer" referrerPolicy="no-referrer">
          {t.asset.attributionChart}
        </a>
        {' · '}
        <a href={COINGECKO_URL} rel="noreferrer" referrerPolicy="no-referrer">
          {t.asset.attributionData}
        </a>
        {' · '}
        <a href="/third-party-notices.txt">{t.asset.attributionNotices}</a>
      </p>
      <TradesTable data={data} />
    </>
  )
}

function ChartSkeleton() {
  // Same height as the chart, so nothing jumps when it arrives; announced once as "Loading…".
  return (
    <div aria-busy="true">
      <span className="visually-hidden">{t.common.loading}</span>
      <div className="chart-skeleton skeleton" aria-hidden="true" />
    </div>
  )
}

function RangeButtons({ value, onChange }: { value: HistoryRange; onChange: (range: HistoryRange) => void }) {
  return (
    <div className="range-group" role="group" aria-label={t.asset.rangeLabel}>
      {HISTORY_RANGES.map((range) => (
        <button
          key={range}
          type="button"
          className="button button-secondary range-button"
          aria-pressed={value === range}
          onClick={() => onChange(range)}
        >
          {t.asset.ranges[range]}
        </button>
      ))}
    </div>
  )
}

// The canvas is drawn for sighted users; screen readers get the caption and the trades table.
function ChartFigure({ data, symbol }: { data: AssetHistory; symbol: string }) {
  const closes = data.bars.map((b) => b.close)
  const low = closes.reduce((a, b) => (Big(b).lt(a) ? b : a))
  const high = closes.reduce((a, b) => (Big(b).gt(a) ? b : a))
  const first = data.bars[0].date
  const last = data.bars[data.bars.length - 1]
  return (
    <figure className="chart-figure">
      <div aria-hidden="true">
        <PriceChart bars={data.bars} markers={data.markers} />
      </div>
      <figcaption className="hint">
        {t.asset.caption(
          symbol,
          formatDay(first),
          formatDay(last.date),
          formatPrice(last.close),
          formatPrice(low),
          formatPrice(high),
        )}{' '}
        {data.markers.length > 0 && t.asset.markersLegend}
      </figcaption>
    </figure>
  )
}

// showRank: the history endpoint returns market-cap ranks; search results don't, and showing
// them as "unranked" would be false.
function CoinPicker({
  symbol,
  candidates,
  body,
  showRank = true,
}: {
  symbol: string
  candidates: CoinCandidate[]
  body: string
  showRank?: boolean
}) {
  return (
    <div className="coin-picker">
      <h3>{t.asset.pickerTitle(symbol)}</h3>
      <p className="muted">{body}</p>
      {candidates.length === 0 ? (
        <p className="muted">{t.asset.noCandidates}</p>
      ) : (
        <ul className="picker-list">
          {candidates.map((c) => (
            <li key={c.id}>
              <Link className="picker-item" to={`?type=crypto&id=${encodeURIComponent(c.id)}`}>
                <span className="picker-name">
                  {c.name} <span className="muted">({c.symbol})</span>
                </span>
                <span className="picker-meta muted">
                  {c.id}
                  {showRank && <> · {c.rank !== null ? t.asset.rank(c.rank) : t.asset.unranked}</>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="hint">{t.asset.pickerNote(symbol)}</p>
    </div>
  )
}

// "Not this one?": the coins search finds for the ticker, exact matches first.
function SearchPicker({ symbol }: { symbol: string }) {
  const search = useAssetSearch(symbol)
  if (search.isPending) return <ChartSkeleton />
  const coins = (search.data?.results ?? []).filter((r) => r.asset_type === 'crypto')
  const exactFirst = [...coins].sort((a, b) => Number(b.symbol === symbol) - Number(a.symbol === symbol))
  const candidates = exactFirst.map((c) => ({ id: c.provider_id, symbol: c.symbol, name: c.name, rank: null }))
  return (
    <CoinPicker symbol={symbol} candidates={candidates} body={t.asset.pickerSearchBody} showRank={false} />
  )
}

function TypeChooser({ symbol }: { symbol: string }) {
  return (
    <div className="coin-picker">
      <h3>{t.asset.typeTitle(symbol)}</h3>
      <p className="muted">{t.asset.typeBody}</p>
      <div className="range-group">
        <Link className="button button-secondary" to="?type=stock">
          {t.asset.stock}
        </Link>
        <Link className="button button-secondary" to="?type=crypto">
          {t.asset.crypto}
        </Link>
      </div>
    </div>
  )
}

const UNDRAWN_TEXT: Record<UndrawnReason, string> = t.asset.undrawn

// Every trade, drawn or not, so nothing depends on seeing the canvas.
function TradesTable({ data }: { data: AssetHistory }) {
  const rows = [
    ...data.markers.map((m) => ({
      id: m.transaction_id,
      day: m.trade_date,
      side: m.side,
      quantity: m.quantity,
      price: m.price,
      status: m.snapped ? t.asset.snapped(formatDay(m.date)) : t.asset.onChart,
    })),
    ...data.undrawn_trades.map((u) => ({
      id: u.transaction_id,
      day: u.trade_date,
      side: u.side,
      quantity: u.quantity,
      price: u.price,
      status: UNDRAWN_TEXT[u.reason],
    })),
  ].sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : 0))

  return (
    <section aria-labelledby="asset-trades-heading" className="asset-trades">
      <h3 id="asset-trades-heading">{t.asset.tradesHeading}</h3>
      {rows.length === 0 ? (
        <p className="muted">{t.asset.tradesEmpty}</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">{t.asset.tradeDate}</th>
                <th scope="col">{t.asset.tradeSide}</th>
                <th scope="col" className="num">{t.asset.tradeQuantity}</th>
                <th scope="col" className="num">{t.asset.tradePrice}</th>
                <th scope="col">{t.asset.tradeOnChart}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="tabular">{formatDay(r.day)}</td>
                  <td>
                    <span className={`side side-${r.side}`}>{t.transactions.sides[r.side]}</span>
                  </td>
                  <td className="num">{r.quantity}</td>
                  <td className="num">{formatPrice(r.price)}</td>
                  <td className="trade-status">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
