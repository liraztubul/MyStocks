import type { Holding } from '../api/portfolio'
import { useHoldings } from '../hooks/usePortfolio'
import { t } from '../strings'
import { DayChange } from './DayChange'
import { formatDateTime, formatMoney, formatPrice, formatSignedMoney, formatSignedPercent, gainClass } from './format'

export function HoldingsTable() {
  const { data: holdings, error, isPending } = useHoldings()

  if (isPending) return <p>{t.common.loading}</p>
  if (error) return <p role="alert">{t.common.loadError(t.holdings.heading, error.message)}</p>
  if (holdings.length === 0) return <p className="muted">{t.holdings.empty}</p>

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>{t.holdings.symbol}</th>
            <th className="num">{t.holdings.quantity}</th>
            <th className="num">{t.holdings.averageCost}</th>
            <th className="num">{t.holdings.price}</th>
            <th className="num">{t.holdings.value}</th>
            <th className="num">{t.holdings.dayChange}</th>
            <th className="num">{t.holdings.unrealized}</th>
            <th className="num">{t.holdings.unrealizedPct}</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <HoldingRow key={h.symbol} holding={h} />
          ))}
        </tbody>
      </table>
      <p className="hint">{t.holdings.footnote}</p>
    </div>
  )
}

function HoldingRow({ holding: h }: { holding: Holding }) {
  const pnlClass = gainClass(h.unrealized_pl)
  return (
    <tr>
      <td>
        {h.symbol} <span className={`tag tag-${h.asset_type}`}>{h.asset_type}</span>
      </td>
      <td className="num">{h.quantity}</td>
      <td className="num">{formatPrice(h.average_cost)}</td>
      <td className="num">
        {h.current_price === null ? (
          <span className="hint warning" title={h.price_unavailable_reason ?? undefined}>
            {t.common.unavailable}
          </span>
        ) : (
          <>
            {formatPrice(h.current_price)}
            {h.price_is_stale && h.price_as_of && (
              <span className="sub warning">{t.holdings.staleSince(formatDateTime(h.price_as_of))}</span>
            )}
          </>
        )}
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
      <td className={`num ${pnlClass ?? ''}`}>
        {h.unrealized_pl === null ? t.common.noValue : formatSignedMoney(h.unrealized_pl)}
      </td>
      <td className={`num ${pnlClass ?? ''}`}>
        {h.unrealized_pl_pct === null ? t.common.noValue : formatSignedPercent(h.unrealized_pl_pct)}
      </td>
    </tr>
  )
}
