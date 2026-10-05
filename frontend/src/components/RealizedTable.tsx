import { useRealizedPl } from '../hooks/usePortfolio'
import { t } from '../strings'
import { formatDate, formatMoney, formatPrice, formatSignedMoney, gainClass } from './format'

export function RealizedTable() {
  const { data, error, isPending } = useRealizedPl()

  if (isPending) return <p>{t.common.loading}</p>
  if (error) return <p role="alert">{t.common.loadError(t.realized.heading, error.message)}</p>
  if (data.sales.length === 0) return <p className="muted">{t.realized.empty}</p>

  // The API already returns sales newest first.
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>{t.realized.date}</th>
            <th>{t.realized.symbol}</th>
            <th className="num">{t.realized.quantity}</th>
            <th className="num">{t.realized.sellPrice}</th>
            <th className="num">{t.realized.fee}</th>
            <th className="num">{t.realized.averageCost}</th>
            <th className="num">{t.realized.proceeds}</th>
            <th className="num">{t.realized.realized}</th>
          </tr>
        </thead>
        <tbody>
          {data.sales.map((sale) => (
            <tr key={sale.transaction_id}>
              <td>{formatDate(sale.executed_at)}</td>
              <td>{sale.symbol}</td>
              <td className="num">{sale.quantity}</td>
              <td className="num">{formatPrice(sale.price)}</td>
              <td className="num">{formatMoney(sale.fee)}</td>
              <td className="num">{formatPrice(sale.average_cost)}</td>
              <td className="num">{formatMoney(sale.proceeds)}</td>
              <td className={`num ${gainClass(sale.realized_pl) ?? ''}`}>{formatSignedMoney(sale.realized_pl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">{t.realized.footnote}</p>
    </div>
  )
}
