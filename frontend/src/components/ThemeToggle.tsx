import { useTheme } from '../hooks/useTheme'
import { t } from '../strings'
import type { ThemePreference } from '../theme'
import { Icon, type IconName } from './Icon'

const OPTIONS: { value: ThemePreference; icon: IconName; label: string }[] = [
  { value: 'light', icon: 'sun', label: t.theme.light },
  { value: 'dark', icon: 'moon', label: t.theme.dark },
  { value: 'system', icon: 'monitor', label: t.theme.system },
]

export function ThemeToggle() {
  const { preference, choose } = useTheme()
  return (
    <div className="segmented" role="group" aria-label={t.theme.label}>
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-label={option.label}
          title={option.label}
          aria-pressed={preference === option.value}
          onClick={() => choose(option.value)}
        >
          <Icon name={option.icon} size={18} />
        </button>
      ))}
    </div>
  )
}
