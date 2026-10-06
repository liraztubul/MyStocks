import Big from 'big.js'
import { useEffect, useState } from 'react'
import { useReducedMotion } from '../hooks/useReducedMotion'

const DURATION_MS = 700
// Count-ups that already ran in this page load, by id: the animation is a first-impression
// flourish, so a 60 s refetch or coming back to the dashboard just shows the new value.
const played = new Set<string>()

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

interface Props {
  id: string
  value: string
  format: (value: string) => string
}

/** Animates from 0 to `value` once, then always shows `value` exactly.
 *
 * Every intermediate frame is computed with big.js; only the easing progress (a fraction of
 * elapsed time, not money) starts as a float, and it enters Big as a fixed 6-place string. When
 * the animation ends the component renders the live `value` prop itself, so the settled number
 * is the API's own string, never the result of frame arithmetic.
 */
export function CountUp({ id, value, format }: Props) {
  const reduced = useReducedMotion()
  // Decided once, on mount. Like a constructor argument: later renders never re-decide it.
  const [animateFrom] = useState(() => (!reduced && !played.has(id) ? value : null))
  // The in-flight frame while animating; null means "show the real value".
  const [frame, setFrame] = useState<string | null>(animateFrom === null ? null : '0')

  useEffect(() => {
    if (animateFrom === null) return
    played.add(id)
    const target = Big(animateFrom)
    const start = performance.now()
    let handle = 0
    const step = (now: number) => {
      const t = Math.min((now - start) / DURATION_MS, 1)
      if (t >= 1) {
        setFrame(null)
        return
      }
      setFrame(target.times(Big(easeOutCubic(t).toFixed(6))).toFixed(2))
      handle = requestAnimationFrame(step)
    }
    handle = requestAnimationFrame(step)
    return () => cancelAnimationFrame(handle)
  }, [animateFrom, id])

  // Reduced motion switched on mid-animation: stop showing frames immediately.
  const shown = frame !== null && !reduced ? frame : value
  return (
    <>
      <span aria-hidden="true">{format(shown)}</span>
      <span className="visually-hidden">{format(value)}</span>
    </>
  )
}
