import { useEffect, useRef, useState } from 'react'
import { t } from '../strings'
import { Icon } from './Icon'
import { Ledgie, Sparkles } from './Ledgie'

const STORAGE_KEY = 'mystocks-first-entry-celebrated'
const AUTO_HIDE_MS = 6_000

// Storage can throw (private mode, blocked site data); then the celebration just isn't remembered.
function alreadyCelebrated(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function rememberCelebrated(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    // Not persisted; the 0 → 1 condition still keeps it to a single moment in this session.
  }
}

/** One-time celebration of the user's FIRST entry: the list going from 0 to 1 in this session.
 * Deliberately blind to what was traded or whether it gained or lost: it marks starting the
 * ledger, not trading activity.
 */
export function FirstEntryCelebration({ count }: { count: number | undefined }) {
  const previous = useRef<number | undefined>(undefined)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (count === undefined) return
    if (previous.current === 0 && count === 1 && !alreadyCelebrated()) {
      rememberCelebrated()
      setVisible(true)
    }
    previous.current = count
  }, [count])

  useEffect(() => {
    if (!visible) return
    const timer = setTimeout(() => setVisible(false), AUTO_HIDE_MS)
    return () => clearTimeout(timer)
  }, [visible])

  if (!visible) return null
  return (
    <div className="celebration card" role="status">
      <div className="celebration-art" aria-hidden="true">
        <Sparkles />
        <Ledgie pose="cheer" size={88} />
      </div>
      <div className="celebration-text">
        <strong>{t.celebration.title}</strong>
        <span className="muted">{t.celebration.body}</span>
      </div>
      <button type="button" className="icon-button" aria-label={t.celebration.dismiss} onClick={() => setVisible(false)}>
        <Icon name="close" size={18} />
      </button>
    </div>
  )
}
