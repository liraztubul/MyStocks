import Big from 'big.js'
import { t } from '../strings'
import { Icon } from './Icon'

// Gain/loss is shown three ways: colour, an arrow and the explicit sign in `text`, so it never
// depends on colour alone.
export function Trend({ value, text, size = 14 }: { value: string; text: string; size?: number }) {
  const amount = Big(value)
  const direction = amount.gt(0) ? 'gain' : amount.lt(0) ? 'loss' : null
  return (
    <span className={`trend ${direction ?? ''}`}>
      {direction && (
        <>
          <Icon name={direction === 'gain' ? 'up' : 'down'} size={size} />
          <span className="visually-hidden">{direction === 'gain' ? t.common.gain : t.common.loss}</span>
        </>
      )}
      {text}
    </span>
  )
}
