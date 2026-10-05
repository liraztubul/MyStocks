import type { ReactNode } from 'react'
import { t } from '../strings'

function Bar({ width, height = 14 }: { width: string; height?: number }) {
  return <span className="skeleton" style={{ inlineSize: width, blockSize: height }} />
}

// Announced once as "Loading…"; the shimmer bars themselves are hidden from assistive tech.
function Busy({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={className} aria-busy="true">
      <span className="visually-hidden">{t.common.loading}</span>
      <div aria-hidden="true">{children}</div>
    </div>
  )
}

export function SummarySkeleton() {
  return (
    <Busy>
      <div className="hero">
        <Bar width="7rem" height={14} />
        <Bar width="14rem" height={44} />
      </div>
      <div className="stat-grid">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card stat">
            <Bar width="5rem" height={12} />
            <Bar width="8rem" height={24} />
          </div>
        ))}
      </div>
    </Busy>
  )
}

export function DonutSkeleton() {
  return (
    <Busy className="donut">
      <span className="skeleton skeleton-ring" />
      <div className="donut-side">
        {[0, 1, 2, 3].map((i) => (
          <Bar key={i} width="100%" height={18} />
        ))}
      </div>
    </Busy>
  )
}

export function RowsSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <Busy className="rows-skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <Bar key={i} width="100%" height={20} />
      ))}
    </Busy>
  )
}
