import { useRealizedPl } from '../hooks/usePortfolio'
import { t } from '../strings'
import { FormError } from './FormError'
import { formatDate, formatMoney, formatPrice, formatSignedMoney } from './format'
import { RowsSkeleton } from './Skeleton'
import { Trend } from './Trend'

// highlightId marks a sale just made from the Sell dialog, with a visible tag, not colour alone.
export function RealizedTable({ highlightId }: { highlightId?: string | null }) {
  const { data, error, isPending } = useRealizedPl()

  if (isPending) return <RowsSkeleton rows={2} />
  if (error) {
    return (
<FormError>{t.common.loadError(t.realized.heading, error.message)}</FormError>
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
              <tr key={sale.transaction_id} className={sale.transaction_id === highlightId ? 'row-new' : undefined}>
                <th scope="row">
                  <span className="symbol-cell">
                    <span className="symbol">{sale.symbol}</span>
                    {sale.transaction_id === highlightId && <span className="tag tag-new">{t.realized.newTag}</span>}
                  </span>
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
