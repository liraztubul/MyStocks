import type { Holding } from '../api/portfolio'
import { useHoldings } from '../hooks/usePortfolio'
import { formatMoney, formatPrice, formatSignedMoney, formatSignedPercent, gainClass } from './format'

export function HoldingsTable() {
  const { data: holdings, error, isPending } = useHoldings()

  if (isPending) return <p>Loading holdings…</p>
  if (error) return <p role="alert">Could not load holdings: {error.message}</p>
  if (holdings.length === 0) return <p>No open positions.</p>

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th className="num">Quantity</th>
            <th className="num">Avg cost</th>
            <th className="num">Price</th>
            <th className="num">Value</th>
            <th className="num">Unrealized P/L</th>
            <th className="num">%</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <HoldingRow key={h.symbol} holding={h} />
          ))}
        </tbody>
      </table>
      <p className="hint">All amounts in USD. Average cost includes buy fees.</p>
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
            unavailable
          </span>
        ) : (
          <>
            {formatPrice(h.current_price)}
            {h.price_is_stale && h.price_as_of && (
              <span className="hint warning stale">
                stale since {new Date(h.price_as_of).toLocaleString()}
              </span>
            )}
          </>
        )}
      </td>
      <td className="num">{h.market_value === null ? '—' : formatMoney(h.market_value)}</td>
      <td className={`num ${pnlClass ?? ''}`}>
        {h.unrealized_pl === null ? '—' : formatSignedMoney(h.unrealized_pl)}
      </td>
      <td className={`num ${pnlClass ?? ''}`}>
        {h.unrealized_pl_pct === null ? '—' : formatSignedPercent(h.unrealized_pl_pct)}
      </td>
    </tr>
  )
}
