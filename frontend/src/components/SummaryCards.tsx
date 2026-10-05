import type { ReactNode } from 'react'
import type { PortfolioSummary } from '../api/portfolio'
import { t } from '../strings'
import { basisLabel } from './dayChangeLabels'
import { formatMoney, formatSignedMoney, formatSignedPercent, gainClass } from './format'

function dayChangeBasisText(summary: PortfolioSummary): string {
  const bases = summary.day_change_bases
  return bases.length === 1 ? basisLabel(bases[0]) : t.dayChange.mixed
}

export function SummaryCards({ summary }: { summary: PortfolioSummary }) {
  const partial = summary.unpriced_symbols.length > 0 || summary.has_stale_prices
  return (
    <>
      <div className="cards">
        <Card label={t.summary.marketValue} value={formatMoney(summary.total_market_value)} />
        <Card label={t.summary.costBasis} value={formatMoney(summary.total_cost_basis)} />
        <Card
          label={t.summary.unrealized}
          value={formatSignedMoney(summary.total_unrealized_pl)}
          detail={
            summary.total_unrealized_pl_pct !== null && (
              <span className={gainClass(summary.total_unrealized_pl)}>
                {formatSignedPercent(summary.total_unrealized_pl_pct)}
              </span>
            )
          }
          tone={gainClass(summary.total_unrealized_pl)}
        />
        <Card
          label={t.summary.realized}
          value={formatSignedMoney(summary.total_realized_pl)}
          tone={gainClass(summary.total_realized_pl)}
        />
        <Card
          label={t.summary.dayChange}
          value={
            summary.total_day_change === null ? t.common.noValue : formatSignedMoney(summary.total_day_change)
          }
          detail={
            summary.total_day_change !== null && (
              <>
                {summary.total_day_change_pct !== null && (
                  <span className={gainClass(summary.total_day_change)}>
                    {formatSignedPercent(summary.total_day_change_pct)} ·{' '}
                  </span>
                )}
                {dayChangeBasisText(summary)} · {t.summary.dayChangeOpenOnly}
              </>
            )
          }
          tone={gainClass(summary.total_day_change)}
        />
      </div>
      {(partial || summary.day_change_unavailable_symbols.length > 0) && (
        <div className="notice" role="status">
          {partial && <strong>{t.summary.partialTotals} </strong>}
          {summary.has_stale_prices && <span>{t.summary.stalePrices} </span>}
          {summary.unpriced_symbols.length > 0 && (
            <span>{t.summary.unpriced(summary.unpriced_symbols.join(', '))} </span>
          )}
          {summary.day_change_unavailable_symbols.length > 0 && (
            <span>{t.summary.dayChangeUnavailable(summary.day_change_unavailable_symbols.join(', '))}</span>
          )}
        </div>
      )}
    </>
  )
}

function Card({
  label,
  value,
  detail,
  tone,
}: {
  label: string
  value: string
  detail?: ReactNode
  tone?: string
}) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className={`card-value ${tone ?? ''}`}>
        {value} <span className="card-unit">{t.common.usd}</span>
      </div>
      {detail && <div className="card-detail">{detail}</div>}
    </div>
  )
}
