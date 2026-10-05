import { useId, useState, type FormEvent } from 'react'
import { Icon } from '../components/Icon'
import { ThemeToggle } from '../components/ThemeToggle'
import { useLogin, useRegister } from '../hooks/useAuth'
import { t } from '../strings'

type Mode = 'login' | 'register'

export function LoginPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const loginMutation = useLogin()
  const registerMutation = useRegister()
  const mutation = mode === 'login' ? loginMutation : registerMutation
  const hintId = useId()

  const passwordsMismatch =
    mode === 'register' && confirmPassword.length > 0 && password !== confirmPassword

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (mode === 'register' && password !== confirmPassword) return
    mutation.mutate({ email, password })
  }

  function toggleMode() {
    setMode(mode === 'login' ? 'register' : 'login')
    setConfirmPassword('')
    loginMutation.reset()
    registerMutation.reset()
  }

  return (
    <div className="auth-page">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      <main className="auth-card card">
        <div className="brand brand-large">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="logo" size={24} />
          </span>
          {t.appName}
        </div>
        <p className="muted auth-tagline">{t.auth.tagline}</p>
        <h1 className="auth-title">{mode === 'login' ? t.auth.logIn : t.auth.createAccount}</h1>
        <form onSubmit={handleSubmit} className="stack">
          <label className="field">
            <span className="field-label">{t.auth.email}</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">{t.auth.password}</span>
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
              minLength={mode === 'register' ? 8 : undefined}
              aria-describedby={mode === 'register' ? hintId : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {mode === 'register' && (
              <span id={hintId} className="field-hint">
                {t.auth.passwordHint}
              </span>
            )}
          </label>
          {mode === 'register' && (
            <label className="field">
              <span className="field-label">{t.auth.confirmPassword}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </label>
          )}
          {passwordsMismatch && (
            <p role="alert" className="form-error">
              {t.auth.passwordsMismatch}
            </p>
          )}
          {mutation.error && (
            <p role="alert" className="form-error">
              {mutation.error.message}
            </p>
          )}
          <button
            type="submit"
            className="button button-primary button-block"
            disabled={mutation.isPending || (mode === 'register' && passwordsMismatch)}
          >
            {mode === 'login' ? t.auth.logIn : t.auth.register}
          </button>
        </form>
        <button type="button" className="button button-ghost button-block" onClick={toggleMode}>
          {mode === 'login' ? t.auth.switchToRegister : t.auth.switchToLogin}
        </button>
      </main>
    </div>
  )
}
