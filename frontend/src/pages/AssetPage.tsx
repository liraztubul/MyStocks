import { Link, useParams } from 'react-router'
import { PageHeading } from '../components/PageHeading'
import { t } from '../strings'

// One page per asset, held or not (a watched symbol isn't a holding). Placeholder for the M6a
// price chart (stage 5); lazily loaded, so the chart library stays out of the main bundle.
export default function AssetPage() {
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
