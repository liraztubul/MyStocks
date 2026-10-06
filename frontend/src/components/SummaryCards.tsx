import type { ReactNode } from 'react'
import type { PortfolioSummary } from '../api/portfolio'
import { t } from '../strings'
import { CountUp } from './CountUp'
import { basisLabel } from './dayChangeLabels'
import { formatMoney, formatSignedMoney, formatSignedPercent } from './format'
import { Icon, type IconName } from './Icon'
import { Trend } from './Trend'

function dayChangeBasisText(summary: PortfolioSummary): string {
  const bases = summary.day_change_bases
  return bases.length === 1 ? basisLabel(bases[0]) : t.dayChange.mixed
}

export function SummaryCards({ summary }: { summary: PortfolioSummary }) {
  const partial = summary.unpriced_symbols.length > 0 || summary.has_stale_prices
  return (
    <>
      <div className="hero">
        <div className="hero-label">{t.summary.marketValue}</div>
        <div className="hero-value num">
          <CountUp id="hero-market-value" value={summary.total_market_value} format={formatMoney} />{' '}
          <span className="unit">{t.common.usd}</span>
        </div>
        {summary.total_day_change !== null && (
          <div className="hero-change">
            <Trend
              value={summary.total_day_change}
              text={`${formatSignedMoney(summary.total_day_change)}${
                summary.total_day_change_pct !== null
                  ? ` (${formatSignedPercent(summary.total_day_change_pct)})`
                  : ''
              }`}
              size={16}
            />
            <span className="muted"> {dayChangeBasisText(summary)}</span>
          </div>
        )}
      </div>
      <div className="stat-grid">
        <Stat label={t.summary.costBasis} icon="wallet" tone="violet">
          {formatMoney(summary.total_cost_basis)}
        </Stat>
        <Stat
          label={t.summary.unrealized}
          icon="chart"
          tone="cyan"
          detail={
            summary.total_unrealized_pl_pct !== null && (
              <Trend
                value={summary.total_unrealized_pl}
                text={formatSignedPercent(summary.total_unrealized_pl_pct)}
                size={12}
              />
            )
          }
        >
          <Trend value={summary.total_unrealized_pl} text={formatSignedMoney(summary.total_unrealized_pl)} size={18} />
        </Stat>
        <Stat label={t.summary.realized} icon="check" tone="sunny">
          <Trend value={summary.total_realized_pl} text={formatSignedMoney(summary.total_realized_pl)} size={18} />
        </Stat>
        <Stat
          label={t.summary.dayChange}
          icon="clock"
          tone="coral"
          detail={
            summary.total_day_change !== null && (
              <>
                {dayChangeBasisText(summary)} · {t.summary.dayChangeOpenOnly}
              </>
            )
          }
        >
          {summary.total_day_change === null ? (
            t.common.noValue
          ) : (
            <Trend value={summary.total_day_change} text={formatSignedMoney(summary.total_day_change)} size={18} />
          )}
        </Stat>
      </div>
      {(partial || summary.day_change_unavailable_symbols.length > 0) && (
        <div className="notice" role="status">
          <Icon name="alert" size={18} className="notice-icon" />
          <div>
            {partial && <strong>{t.summary.partialTotals} </strong>}
            {summary.has_stale_prices && <span>{t.summary.stalePrices} </span>}
            {summary.unpriced_symbols.length > 0 && (
              <span>{t.summary.unpriced(summary.unpriced_symbols.join(', '))} </span>
            )}
            {summary.day_change_unavailable_symbols.length > 0 && (
              <span>{t.summary.dayChangeUnavailable(summary.day_change_unavailable_symbols.join(', '))}</span>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// Accent hues only decorate the icon chip; the number itself stays text, gain or loss coloured.
type Tone = 'violet' | 'cyan' | 'sunny' | 'coral'

function Stat({
  label,
  icon,
  tone,
  detail,
  children,
}: {
  label: string
  icon: IconName
  tone: Tone
  detail?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="card stat">
      <div className="stat-head">
        <span className={`chip-icon chip-${tone}`} aria-hidden="true">
          <Icon name={icon} size={18} />
        </span>
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value num">
        {children}
        {children !== t.common.noValue && <span className="unit"> {t.common.usd}</span>}
      </div>
      {detail && <div className="stat-detail">{detail}</div>}
    </div>
  )
}
