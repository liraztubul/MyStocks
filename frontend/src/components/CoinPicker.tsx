import { Link } from 'react-router'
import type { CoinCandidate } from '../api/history'
import { t } from '../strings'

interface Props {
  symbol: string
  candidates: CoinCandidate[]
  body: string
  note: string
  // The history endpoint returns market-cap ranks; search results and add errors don't, and
  // showing them as "unranked" would be false.
  showRank?: boolean
  // A coin is picked either by following a link or by a callback (a form re-submitting).
  pickHref?: (id: string) => string
  onPick?: (id: string) => void
  disabled?: boolean
}

export function CoinPicker({ symbol, candidates, body, note, showRank = true, pickHref, onPick, disabled }: Props) {
  return (
    <div className="coin-picker">
      <h3>{t.asset.pickerTitle(symbol)}</h3>
      <p className="muted">{body}</p>
      {candidates.length === 0 ? (
        <p className="muted">{t.asset.noCandidates}</p>
      ) : (
        <ul className="picker-list">
          {candidates.map((c) => {
            const content = (
              <>
                <span className="picker-name">
                  {c.name} <span className="muted">({c.symbol})</span>
                </span>
                <span className="picker-meta muted">
                  {c.id}
                  {showRank && <> · {c.rank !== null ? t.asset.rank(c.rank) : t.asset.unranked}</>}
                </span>
              </>
            )
            return (
              <li key={c.id}>
                {onPick ? (
                  <button type="button" className="picker-item" disabled={disabled} onClick={() => onPick(c.id)}>
                    {content}
                  </button>
                ) : (
                  <Link className="picker-item" to={pickHref?.(c.id) ?? '#'}>
                    {content}
                  </Link>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <p className="hint">{note}</p>
    </div>
  )
}
