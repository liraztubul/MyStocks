import { Link, useParams } from 'react-router'
import { PageHeading } from '../components/PageHeading'
import { t } from '../strings'

// Placeholder for the M6a price chart (stage 5). Lazily loaded, so the chart library stays out of
// the main bundle once it lands.
export default function HoldingPage() {
  const symbol = (useParams().symbol ?? '').toUpperCase()
  return (
    <section className="card section" aria-labelledby="holding-heading">
      <PageHeading title={symbol} />
      <h2 id="holding-heading">{symbol}</h2>
      <p className="muted">{t.holding.chartComingSoon}</p>
      <Link className="button button-ghost page-action" to="/">
        {t.holding.backToDashboard}
      </Link>
    </section>
  )
}
