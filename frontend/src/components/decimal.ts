// The API stores Numeric(28, 10): plain digits, an optional dot, at most 10 decimal places.
export const DECIMAL_PATTERN = '\\d+(\\.\\d{1,10})?'

const DECIMAL = new RegExp(`^${DECIMAL_PATTERN}$`)

export function isDecimal(value: string): boolean {
  return DECIMAL.test(value)
}
