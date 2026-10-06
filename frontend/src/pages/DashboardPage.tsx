import { useRef, useState } from 'react'
import type { Holding } from '../api/portfolio'
import type { Transaction } from '../api/transactions'
import { AllocationDonut } from '../components/AllocationDonut'
import { EmptyState } from '../components/EmptyState'
import { FormError } from '../components/FormError'
import { HoldingsTable } from '../components/HoldingsTable'
import { PageHeading } from '../components/PageHeading'
import { Icon } from '../components/Icon'
import { RealizedTable } from '../components/RealizedTable'
import { SellDialog } from '../components/SellDialog'
import { DonutSkeleton, SummarySkeleton } from '../components/Skeleton'
import { SummaryCards } from '../components/SummaryCards'
import { useHoldings, useRealizedPl, useSummary } from '../hooks/usePortfolio'
import { t } from '../strings'

export function DashboardPage() {
  const summary = useSummary()
  // Same queries the tables use (shared cache), read here only to pick the empty state.
  const holdings = useHoldings()
  const realized = useRealizedPl()
  const hasNoActivity = holdings.data?.length === 0 && realized.data?.sales.length === 0

  // The dialog lives here, not inside HoldingsTable: selling the last unit empties that table,
  // and the dialog (and its request) must outlive the row it was opened from.
  const [selling, setSelling] = useState<Holding | null>(null)
  const [lastSale, setLastSale] = useState<Transaction | null>(null)
  const realizedHeading = useRef<HTMLHeadingElement>(null)

  // Derived from the refetched holdings at render time, not computed from the sale: the server
  // decides whether a position is closed.
  const closedPosition = lastSale !== null && holdings.data?.some((h) => h.symbol === lastSale.symbol) === false

  function handleSold(sale: Transaction) {
    setLastSale(sale)
    setSelling(null)
  }

  function showTrade() {
    realizedHeading.current?.scrollIntoView({ block: 'start' })
    realizedHeading.current?.focus()
  }

  return (
    <>
      <PageHeading title={t.nav.dashboard} />
      <section aria-labelledby="summary-heading" className="summary">
        <h2 id="summary-heading" className="visually-hidden">
          {t.summary.heading}
        </h2>
        {summary.isPending && <SummarySkeleton />}
        {summary.error && <FormError>{t.common.loadError(t.summary.heading, summary.error.message)}</FormError>}
        {summary.data && <SummaryCards summary={summary.data} />}
      </section>
      {hasNoActivity ? (
        <EmptyState />
      ) : (
        <>
          <section aria-labelledby="allocation-heading" className="card section">
            <h2 id="allocation-heading">{t.allocation.heading}</h2>
            {summary.isPending ? <DonutSkeleton /> : summary.data && <AllocationDonut summary={summary.data} />}
          </section>
          <section aria-labelledby="holdings-heading" className="card section">
            <h2 id="holdings-heading">{t.holdings.heading}</h2>
            <div role="status" className="sale-status-region">
              {lastSale && (
                <div className="sale-status">
                  <Icon name="check" size={18} className="sale-status-icon" />
                  <p>
                    {t.sell.sold(lastSale.quantity, lastSale.symbol)}
                    {closedPosition && ` ${t.sell.soldAll(lastSale.symbol)}`}
                  </p>
                  <div className="sale-status-actions">
                    <button type="button" className="button button-ghost" onClick={showTrade}>
                      {t.sell.showTrade}
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={t.sell.dismiss}
                      onClick={() => setLastSale(null)}
                    >
                      <Icon name="close" size={18} />
                    </button>
                  </div>
                </div>
              )}
            </div>
            <HoldingsTable onSell={setSelling} />
          </section>
          <section aria-labelledby="realized-heading" className="card section">
            <h2 id="realized-heading" ref={realizedHeading} tabIndex={-1}>
              {t.realized.heading}
            </h2>
            <RealizedTable highlightId={lastSale?.id} />
          </section>
        </>
      )}
      {selling && (
        <SellDialog
          key={selling.symbol}
          holding={selling}
          onSold={handleSold}
          onCancel={() => setSelling(null)}
          fallbackFocus={realizedHeading}
        />
      )}
    </>
  )
}
