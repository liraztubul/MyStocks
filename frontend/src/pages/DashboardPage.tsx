import { AllocationDonut } from '../components/AllocationDonut'
import { EmptyState } from '../components/EmptyState'
import { HoldingsTable } from '../components/HoldingsTable'
import { RealizedTable } from '../components/RealizedTable'
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

  return (
    <>
      <section aria-labelledby="summary-heading" className="summary">
        <h2 id="summary-heading" className="visually-hidden">
          {t.summary.heading}
        </h2>
        {summary.isPending && <SummarySkeleton />}
        {summary.error && (
          <p role="alert" className="form-error">
            {t.common.loadError(t.summary.heading, summary.error.message)}
          </p>
        )}
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
            <HoldingsTable />
          </section>
          <section aria-labelledby="realized-heading" className="card section">
            <h2 id="realized-heading">{t.realized.heading}</h2>
            <RealizedTable />
          </section>
        </>
      )}
    </>
  )
}
