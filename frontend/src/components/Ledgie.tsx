// Ledgie, MyStocks' mascot: an original character (a friendly notebook with a ribbon bookmark),
// drawn here from scratch. Always decorative, so hidden from assistive tech. Colours come from
// CSS classes mapped to theme tokens, never inline styles (keeps the CSP strict).

export type LedgiePose = 'wave' | 'coin' | 'page' | 'cheer' | 'mark'

interface Props {
  pose?: LedgiePose
  size?: number
  className?: string
}

function Arm({ from, to }: { from: [number, number]; to: [number, number] }) {
  return <line className="lg-limb" x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} />
}

export function Ledgie({ pose = 'wave', size = 160, className }: Props) {
  // The brand mark is just the cover and face, cropped tight.
  const viewBox = pose === 'mark' ? '40 18 82 108' : '0 0 160 160'
  return (
    <svg
      viewBox={viewBox}
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={`ledgie ledgie-${pose}${className ? ` ${className}` : ''}`}
    >
      {pose !== 'mark' && <ellipse className="lg-shadow" cx="86" cy="134" rx="40" ry="6" />}

      {/* Limbs behind the body */}
      {pose === 'wave' && (
        <>
          <Arm from={[48, 76]} to={[34, 94]} />
          <Arm from={[114, 70]} to={[134, 46]} />
        </>
      )}
      {pose === 'coin' && (
        <>
          <Arm from={[48, 76]} to={[34, 94]} />
          <Arm from={[114, 76]} to={[134, 80]} />
        </>
      )}
      {pose === 'cheer' && (
        <>
          <Arm from={[48, 70]} to={[30, 44]} />
          <Arm from={[114, 70]} to={[134, 44]} />
        </>
      )}
      {pose !== 'mark' && (
        <>
          <ellipse className="lg-foot" cx="70" cy="126" rx="11" ry="6" />
          <ellipse className="lg-foot" cx="102" cy="126" rx="11" ry="6" />
        </>
      )}

      {/* Ribbon bookmark peeking out of the top */}
      <path className="lg-ribbon" d="M94 18 h11 v24 l-5.5 -5 l-5.5 5 Z" />

      {/* Notebook: page edges, cover, spine */}
      <rect className="lg-pages" x="50" y="30" width="70" height="92" rx="12" />
      <rect className="lg-cover" x="44" y="26" width="72" height="96" rx="14" />
      <rect className="lg-spine" x="44" y="26" width="18" height="96" rx="14" />
      <rect className="lg-spine" x="54" y="26" width="8" height="96" />
      <rect className="lg-label" x="70" y="96" width="34" height="12" rx="5" />

      {/* Face */}
      <circle className="lg-cheek" cx="70" cy="76" r="5.5" />
      <circle className="lg-cheek" cx="104" cy="76" r="5.5" />
      <ellipse className="lg-ink" cx="76" cy="62" rx="4" ry="5" />
      <ellipse className="lg-ink" cx="98" cy="62" rx="4" ry="5" />
      <circle className="lg-shine" cx="77.5" cy="60" r="1.4" />
      <circle className="lg-shine" cx="99.5" cy="60" r="1.4" />
      <path className="lg-smile" d={pose === 'cheer' ? 'M76 74 Q87 90 98 74 Z' : 'M77 75 Q87 84 97 75'} />

      {/* Props in front */}
      {pose === 'coin' && (
        <g className="lg-coin-group">
          <circle className="lg-coin" cx="140" cy="80" r="13" />
          <circle className="lg-coin-rim" cx="140" cy="80" r="8.5" />
          <path className="lg-coin-shine" d="M134 74 q3 -4 8 -4" />
        </g>
      )}
      {pose === 'page' && (
        <>
          <g className="lg-sheet-group">
            <rect className="lg-sheet" x="56" y="82" width="62" height="42" rx="5" />
            <line className="lg-sheet-line" x1="64" y1="94" x2="104" y2="94" />
            <line className="lg-sheet-line" x1="64" y1="103" x2="110" y2="103" />
            <line className="lg-sheet-line" x1="64" y1="112" x2="92" y2="112" />
          </g>
          <Arm from={[48, 82]} to={[58, 98]} />
          <Arm from={[114, 82]} to={[116, 98]} />
        </>
      )}
    </svg>
  )
}

// Small decorative sparkles around an illustration. CSS animates them; reduced motion stops them.
export function Sparkles({ className }: { className?: string }) {
  const star = 'M0 -7 C1 -1 1 -1 7 0 C1 1 1 1 0 7 C-1 1 -1 1 -7 0 C-1 -1 -1 -1 0 -7 Z'
  const spots: [number, number, number, string][] = [
    // Kept at least 12 units from every edge so no sparkle is clipped by its container.
    [24, 34, 1, 'violet'],
    [138, 28, 0.8, 'sunny'],
    [146, 112, 1.1, 'coral'],
    [16, 104, 0.7, 'cyan'],
    [112, 18, 0.6, 'violet'],
  ]
  return (
    <svg viewBox="0 0 160 140" aria-hidden="true" focusable="false" className={`sparkles${className ? ` ${className}` : ''}`}>
      {/* Position lives on the group: a CSS transform animation on the path itself would override
          an SVG transform attribute and snap every star to the origin. */}
      {spots.map(([x, y, scale, tone], i) => (
        <g key={i} transform={`translate(${x} ${y}) scale(${scale})`}>
          <path className={`sparkle sparkle-${tone} sparkle-${i}`} d={star} />
        </g>
      ))}
    </svg>
  )
}
