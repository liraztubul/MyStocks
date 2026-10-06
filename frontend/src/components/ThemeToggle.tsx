import { useTheme } from '../hooks/useTheme'
import { t } from '../strings'
import type { Theme } from '../theme'
import { Icon, type IconName } from './Icon'

const OPTIONS: { value: Theme; icon: IconName; label: string }[] = [
  { value: 'light', icon: 'sun', label: t.theme.light },
  { value: 'dark', icon: 'moon', label: t.theme.dark },
]

export function ThemeToggle() {
  const { theme, choose } = useTheme()
  const active = OPTIONS.findIndex((option) => option.value === theme)
  return (
    // Two toggle buttons in a labelled group; the pressed one is the theme on screen (the OS's,
    // until the user picks). The thumb's position is a data attribute + CSS (no inline style),
    // so it stays CSP-clean and springs between options.
    <div className="segmented" role="group" aria-label={t.theme.label} data-active={active}>
      <span className="segmented-thumb" aria-hidden="true" />
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-label={option.label}
          title={option.label}
          aria-pressed={theme === option.value}
          onClick={() => choose(option.value)}
        >
          <Icon name={option.icon} size={18} />
        </button>
      ))}
    </div>
  )
}
