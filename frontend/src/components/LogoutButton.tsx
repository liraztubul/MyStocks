import { useLogout } from '../hooks/useAuth'
import { t } from '../strings'
import { Icon } from './Icon'

// Icon only on phones, where the header has no room for text; the aria-label names it either way.
export function LogoutButton() {
  const logout = useLogout()
  return (
    <button
      type="button"
      className="button logout-button"
      aria-label={t.auth.logOut}
      title={t.auth.logOut}
      onClick={() => void logout()}
    >
      <Icon name="logout" size={20} />
      <span className="logout-label">{t.auth.logOut}</span>
    </button>
  )
}
