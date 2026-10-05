import Big from 'big.js'
import { useState } from 'react'
import type { PortfolioSummary } from '../api/portfolio'
import { t } from '../strings'
import { formatMoney } from './format'

// Part-to-whole reads at a glance only up to ~6 slices; the rest fold into "Other".
const MAX_NAMED = 5
const RADIUS = 40
const STROKE = 16
const GAP_PX = 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

interface Segment {
  key: string
  label: string
  value: string
  pct: string
  colorVar: string
}

function buildSegments(allocation: PortfolioSummary['allocation']): Segment[] {
  const byValue = [...allocation].sort((a, b) => Big(b.market_value).cmp(a.market_value))
  const named = byValue.length > MAX_NAMED + 1 ? byValue.slice(0, MAX_NAMED) : byValue
  const rest = byValue.slice(named.length)
  // Ring order is alphabetical, not by size: each color then sits next to the neighbours it
  // was validated against, and a symbol keeps its color while the set of holdings is unchanged.
  const segments: Segment[] = [...named]
    .sort((a, b) => a.symbol.localeCompare(b.symbol))
    .map((a, i) => ({
      key: a.symbol,
      label: a.symbol,
      value: a.market_value,
      pct: a.allocation_pct,
      colorVar: `var(--series-${i + 1})`,
    }))
  if (rest.length > 0) {
    segments.push({
      key: '__other',
      label: `${t.allocation.other} (${rest.length})`,
      value: rest.reduce((sum, a) => sum.plus(a.market_value), Big(0)).toString(),
      pct: rest.reduce((sum, a) => sum.plus(a.allocation_pct), Big(0)).toString(),
      colorVar: 'var(--series-other)',
    })
  }
  return segments
}

export function AllocationDonut({ summary }: { summary: PortfolioSummary }) {
  const [active, setActive] = useState<string | null>(null)
  if (summary.allocation.length === 0) return <p className="muted">{t.allocation.empty}</p>

  const segments = buildSegments(summary.allocation)
  const total = Big(summary.total_market_value)
  const gap = segments.length > 1 ? (GAP_PX / CIRCUMFERENCE) * 100 : 0
  const focused = segments.find((s) => s.key === active)

  // Geometry only: arc lengths need numbers; displayed amounts stay Decimal strings.
  const shares = segments.map((s) => (total.gt(0) ? Big(s.value).div(total).times(100).toNumber() : 0))
  const arcs = segments.map((segment, i) => ({
    segment,
    start: shares.slice(0, i).reduce((sum, share) => sum + share, 0),
    length: Math.max(shares[i] - gap, 0.0001),
  }))

  return (
    <div className="donut" onMouseLeave={() => setActive(null)}>
      <svg viewBox="0 0 100 100" role="img" aria-label={t.allocation.chartLabel} className="donut-svg">
        <g transform="rotate(-90 50 50)">
          {arcs.map(({ segment, start, length }) => (
            <circle
              key={segment.key}
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              stroke={segment.colorVar}
              strokeWidth={active === segment.key ? STROKE + 3 : STROKE}
              pathLength={100}
              strokeDasharray={`${length} ${100 - length}`}
              strokeDashoffset={-start}
              opacity={active && active !== segment.key ? 0.45 : 1}
              onMouseEnter={() => setActive(segment.key)}
            >
              <title>{`${segment.label}: ${formatMoney(segment.value)} ${t.common.usd} (${Big(segment.pct).toFixed(2)}%)`}</title>
            </circle>
          ))}
        </g>
        <text x="50" y="48" textAnchor="middle" className="donut-center-label">
          {focused ? focused.label : t.summary.marketValue}
        </text>
        <text x="50" y="58" textAnchor="middle" className="donut-center-value">
          {focused ? `${Big(focused.pct).toFixed(1)}%` : formatMoney(summary.total_market_value)}
        </text>
      </svg>
      <div className="donut-side">
        <ul className="legend">
        {segments.map((segment) => (
          <li
            key={segment.key}
            tabIndex={0}
            className={active === segment.key ? 'active' : undefined}
            onMouseEnter={() => setActive(segment.key)}
            onFocus={() => setActive(segment.key)}
            onBlur={() => setActive(null)}
          >
            <span className="swatch" style={{ background: segment.colorVar }} aria-hidden="true" />
            <span className="legend-label">{segment.label}</span>
            <span className="legend-pct">{Big(segment.pct).toFixed(2)}%</span>
            <span className="legend-value">{formatMoney(segment.value)}</span>
          </li>
        ))}
        </ul>
        <p className="hint">{t.allocation.excludesUnpriced}</p>
      </div>
    </div>
  )
}
