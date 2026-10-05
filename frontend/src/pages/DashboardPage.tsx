import { AllocationDonut } from '../components/AllocationDonut'
import { HoldingsTable } from '../components/HoldingsTable'
import { RealizedTable } from '../components/RealizedTable'
import { SummaryCards } from '../components/SummaryCards'
import { useSummary } from '../hooks/usePortfolio'
import { t } from '../strings'

export function DashboardPage() {
  const summary = useSummary()

  return (
    <>
      <section aria-labelledby="summary-heading">
        <h2 id="summary-heading" className="visually-hidden">
          {t.summary.heading}
        </h2>
        {summary.isPending && <p>{t.common.loading}</p>}
        {summary.error && <p role="alert">{t.common.loadError(t.summary.heading, summary.error.message)}</p>}
        {summary.data && <SummaryCards summary={summary.data} />}
      </section>
      <section aria-labelledby="allocation-heading">
        <h2 id="allocation-heading">{t.allocation.heading}</h2>
        {summary.data && <AllocationDonut summary={summary.data} />}
      </section>
      <section aria-labelledby="holdings-heading">
        <h2 id="holdings-heading">{t.holdings.heading}</h2>
        <HoldingsTable />
      </section>
      <section aria-labelledby="realized-heading">
        <h2 id="realized-heading">{t.realized.heading}</h2>
        <RealizedTable />
      </section>
    </>
  )
}
