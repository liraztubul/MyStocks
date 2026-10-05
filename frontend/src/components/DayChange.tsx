import type { DayChangeBasis } from '../api/portfolio'
import { t } from '../strings'
import { basisLabel, referenceLabel } from './dayChangeLabels'
import { formatSignedMoney, formatSignedPercent, gainClass } from './format'

interface Props {
  amount: string | null
  pct: string | null
  basis: DayChangeBasis | null
  referenceAt: string | null
}

// The basis label is always shown with the number: stock and crypto changes aren't measured
// from the same kind of point, and before the open a stock's "previous close" is days old.
export function DayChange({ amount, pct, basis, referenceAt }: Props) {
  if (amount === null || basis === null) return <span className="muted">{t.common.noValue}</span>
  return (
    <span>
      <span className={gainClass(amount)}>
        {formatSignedMoney(amount)}
        {pct !== null && ` (${formatSignedPercent(pct)})`}
      </span>
      <span className="sub">
        {referenceAt ? referenceLabel(basis, referenceAt) : basisLabel(basis)}
      </span>
    </span>
  )
}
