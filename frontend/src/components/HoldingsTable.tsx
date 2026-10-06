import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { Holding } from '../api/portfolio'
import { NOT_AVAILABLE_ON_DEPLOYMENT } from '../api/writeErrors'
import { useHoldings } from '../hooks/usePortfolio'
import { t } from '../strings'
import { assetPath } from './assetLinks'
import { DayChange } from './DayChange'
import { FormError } from './FormError'
import { formatDateTime, formatMoney, formatPrice, formatSignedMoney, formatSignedPercent } from './format'
import { RowsSkeleton } from './Skeleton'
import { Trend } from './Trend'

export function HoldingsTable({ onSell }: { onSell: (holding: Holding) => void }) {
  const { data: holdings, error, isPending } = useHoldings()

  if (isPending) return <RowsSkeleton rows={5} />
  if (error) {
    return (
<FormError>{t.common.loadError(t.holdings.heading, error.message)}</FormError>
    )
  }
  // The dashboard shows the empty state when there's no activity at all, so an empty list here
  // means every position has been sold.
  if (holdings.length === 0) return <p className="muted">{t.holdings.allClosed}</p>

  return (
    <>
      {/* Two layouts of the same rows: CSS shows the table from 1200px and the cards below it. */}
      <div className="table-scroll holdings-table">
        <table className="data-table sticky-first">
          <thead>
            <tr>
              <th scope="col">{t.holdings.symbol}</th>
              <th scope="col" className="num">{t.holdings.quantity}</th>
              <th scope="col" className="num">{t.holdings.averageCost}</th>
              <th scope="col" className="num">{t.holdings.price}</th>
              <th scope="col" className="num">{t.holdings.value}</th>
              <th scope="col" className="num">{t.holdings.dayChange}</th>
              <th scope="col" className="num">{t.holdings.unrealized}</th>
              <th scope="col" className="num">{t.holdings.unrealizedPct}</th>
              <th scope="col">
                <span className="visually-hidden">{t.holdings.actions}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={h.symbol}>
                <th scope="row">
                  <SymbolCell holding={h} />
                </th>
                <td className="num">{h.quantity}</td>
                <td className="num">{formatPrice(h.average_cost)}</td>
                <td className="num">
                  <PriceCell holding={h} />
                </td>
                <td className="num">{h.market_value === null ? t.common.noValue : formatMoney(h.market_value)}</td>
                <td className="num">
                  <DayChange
                    amount={h.day_change}
                    pct={h.day_change_pct}
                    basis={h.day_change_basis}
                    referenceAt={h.day_change_reference_at}
                  />
                </td>
                <td className="num">
                  {h.unrealized_pl === null ? (
                    t.common.noValue
                  ) : (
                    <Trend value={h.unrealized_pl} text={formatSignedMoney(h.unrealized_pl)} />
                  )}
                </td>
                <td className="num">
                  {h.unrealized_pl === null || h.unrealized_pl_pct === null ? (
                    t.common.noValue
                  ) : (
                    <Trend value={h.unrealized_pl} text={formatSignedPercent(h.unrealized_pl_pct)} />
                  )}
                </td>
                <td>
                  <SellButton holding={h} onSell={onSell} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="holding-cards">
        {holdings.map((h) => (
          <li key={h.symbol} className="holding-card">
            <div className="holding-card-top">
              <SymbolCell holding={h} />
              <span className="holding-card-value num">
                {h.market_value === null ? t.common.noValue : formatMoney(h.market_value)}
              </span>
            </div>
            <dl className="holding-card-grid">
              <Detail label={t.holdings.quantity}>{h.quantity}</Detail>
              <Detail label={t.holdings.averageCost}>{formatPrice(h.average_cost)}</Detail>
              <Detail label={t.holdings.price}>
                <PriceCell holding={h} />
              </Detail>
              <Detail label={t.holdings.unrealized}>
                {h.unrealized_pl === null ? (
                  t.common.noValue
                ) : (
                  <Trend
                    value={h.unrealized_pl}
                    text={`${formatSignedMoney(h.unrealized_pl)}${
                      h.unrealized_pl_pct !== null ? ` (${formatSignedPercent(h.unrealized_pl_pct)})` : ''
                    }`}
                  />
                )}
              </Detail>
              <Detail label={t.holdings.dayChange} wide>
                <DayChange
                  amount={h.day_change}
                  pct={h.day_change_pct}
                  basis={h.day_change_basis}
                  referenceAt={h.day_change_reference_at}
                />
              </Detail>
            </dl>
            <div className="holding-card-actions">
              <SellButton holding={h} onSell={onSell} />
            </div>
          </li>
        ))}
      </ul>
      <p className="hint">{t.holdings.footnote}</p>
      {holdings.some((h) => h.coin_auto_picked) && <p className="hint">{t.holdings.autoPickedNote}</p>}
    </>
  )
}

function SellButton({ holding, onSell }: { holding: Holding; onSell: (holding: Holding) => void }) {
  return (
    <button
      type="button"
      className="button button-secondary button-sell"
      aria-label={t.holdings.sellLabel(holding.symbol)}
      aria-haspopup="dialog"
      onClick={() => onSell(holding)}
    >
      {t.holdings.sell}
    </button>
  )
}

function SymbolCell({ holding: h }: { holding: Holding }) {
  return (
    <span className="symbol-stack">
      <span className="symbol-cell">
        <Link
          className="symbol symbol-link"
          to={assetPath(h.symbol, h.asset_type, h.asset_type === 'crypto' ? h.coin_id : null)}
          aria-label={t.holdings.assetLink(h.symbol)}
        >
          {h.symbol}
        </Link>
        <span className={`tag tag-${h.asset_type}`}>{h.asset_type}</span>
      </span>
      {/* Never a silent guess: say which coin was chosen for the user. */}
      {h.coin_auto_picked && (
        <span className="sub coin-note">{t.holdings.autoPicked(h.coin_name ?? h.coin_id ?? h.symbol)}</span>
      )}
    </span>
  )
}

function PriceCell({ holding: h }: { holding: Holding }) {
  if (h.current_price === null && h.price_unavailable_code === NOT_AVAILABLE_ON_DEPLOYMENT) {
    return <span className="muted price-note">{t.stockData.label}</span>
  }
  if (h.current_price === null) {
    return (
      <span className="warning-text" title={h.price_unavailable_reason ?? undefined}>
        {t.common.unavailable}
      </span>
    )
  }
  return (
    <>
      {formatPrice(h.current_price)}
      {h.price_is_stale && h.price_as_of && (
        <span className="sub warning-text">{t.holdings.staleSince(formatDateTime(h.price_as_of))}</span>
      )}
    </>
  )
}

function Detail({ label, wide, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={wide ? 'detail detail-wide' : 'detail'}>
      <dt>{label}</dt>
      <dd className="num">{children}</dd>
    </div>
  )
}
