import { Link } from 'react-router'
import { t } from '../strings'
import { Icon } from './Icon'
import { Ledgie } from './Ledgie'

export function EmptyState() {
  return (
    <section className="card empty-state" aria-labelledby="empty-title">
      <div className="empty-art" aria-hidden="true">
        <Ledgie pose="page" size={170} />
      </div>
      <h2 id="empty-title">{t.empty.title}</h2>
      <p className="muted">{t.empty.body}</p>
      <Link className="button button-primary" to="/transactions">
        <Icon name="plus" size={18} />
        {t.empty.action}
      </Link>
    </section>
  )
}
