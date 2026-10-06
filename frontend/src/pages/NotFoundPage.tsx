import { Link } from 'react-router'
import { PageHeading } from '../components/PageHeading'
import { t } from '../strings'

export function NotFoundPage() {
  return (
    <section className="card section" aria-labelledby="not-found-heading">
      <PageHeading title={t.notFound.title} />
      <h2 id="not-found-heading">{t.notFound.title}</h2>
      <p className="muted">{t.notFound.body}</p>
      <Link className="button button-primary page-action" to="/">
        {t.holding.backToDashboard}
      </Link>
    </section>
  )
}
