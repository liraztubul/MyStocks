import { t } from '../strings'
import { Icon } from './Icon'

export function EmptyState() {
  return (
    <section className="card empty-state" aria-labelledby="empty-title">
      <div className="empty-art" aria-hidden="true">
        <Icon name="logo" size={40} />
      </div>
      <h2 id="empty-title">{t.empty.title}</h2>
      <p className="muted">{t.empty.body}</p>
      <a className="button button-primary" href="#/transactions">
        <Icon name="plus" size={18} />
        {t.empty.action}
      </a>
    </section>
  )
}
