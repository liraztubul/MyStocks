import { useRealizedPl } from '../hooks/usePortfolio'
import { t } from '../strings'
import { formatDate, formatMoney, formatPrice, formatSignedMoney } from './format'
import { RowsSkeleton } from './Skeleton'
import { Trend } from './Trend'

export function RealizedTable() {
  const { data, error, isPending } = useRealizedPl()

  if (isPending) return <RowsSkeleton rows={2} />
  if (error) {
    return (
      <p role="alert" className="form-error">
        {t.common.loadError(t.realized.heading, error.message)}
      </p>
    )
  }
  if (data.sales.length === 0) return <p className="muted">{t.realized.empty}</p>

  // The API already returns sales newest first. Symbol leads and stays pinned while the rest
  // of a wide row scrolls on narrow screens.
  return (
    <>
      <div className="table-scroll">
        <table className="data-table sticky-first">
          <thead>
            <tr>
              <th scope="col">{t.realized.symbol}</th>
              <th scope="col">{t.realized.date}</th>
              <th scope="col" className="num">{t.realized.quantity}</th>
              <th scope="col" className="num">{t.realized.sellPrice}</th>
              <th scope="col" className="num">{t.realized.fee}</th>
              <th scope="col" className="num">{t.realized.averageCost}</th>
              <th scope="col" className="num">{t.realized.proceeds}</th>
              <th scope="col" className="num">{t.realized.realized}</th>
            </tr>
          </thead>
          <tbody>
            {data.sales.map((sale) => (
              <tr key={sale.transaction_id}>
                <th scope="row">
                  <span className="symbol">{sale.symbol}</span>
                </th>
                <td className="tabular">{formatDate(sale.executed_at)}</td>
                <td className="num">{sale.quantity}</td>
                <td className="num">{formatPrice(sale.price)}</td>
                <td className="num">{formatMoney(sale.fee)}</td>
                <td className="num">{formatPrice(sale.average_cost)}</td>
                <td className="num">{formatMoney(sale.proceeds)}</td>
                <td className="num">
                  <Trend value={sale.realized_pl} text={formatSignedMoney(sale.realized_pl)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">{t.realized.footnote}</p>
    </>
  )
}
