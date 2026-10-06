import { useId, useState, type FormEvent } from 'react'
import { isServerWaking } from '../api/client'
import { Ledgie, Sparkles } from '../components/Ledgie'
import { ServerWakeNotice } from '../components/ServerWakeNotice'
import { ThemeToggle } from '../components/ThemeToggle'
import { useLogin, useRegister } from '../hooks/useAuth'
import { t } from '../strings'

type Mode = 'login' | 'register'

export function LoginPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const loginMutation = useLogin()
  const registerMutation = useRegister()
  const mutation = mode === 'login' ? loginMutation : registerMutation
  const hintId = useId()
  const inviteHintId = useId()

  const passwordsMismatch =
    mode === 'register' && confirmPassword.length > 0 && password !== confirmPassword

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (mode === 'register') {
      if (password !== confirmPassword) return
      registerMutation.mutate({ email, password, invite_code: inviteCode })
    } else {
      loginMutation.mutate({ email, password })
    }
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
        <div className="auth-hero" aria-hidden="true">
          <Sparkles />
          <Ledgie pose="coin" size={150} />
        </div>
        <div className="brand brand-large">{t.appName}</div>
        <p className="muted auth-tagline">{t.auth.tagline}</p>
        <h1 className="auth-title">
          {mode === 'login' ? t.auth.welcome : t.auth.welcomeNew}
          <span className="visually-hidden"> {mode === 'login' ? t.auth.logIn : t.auth.createAccount}</span>
        </h1>
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
          {mode === 'register' && (
            <label className="field">
              <span className="field-label">{t.auth.inviteCode}</span>
              <input
                type="text"
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                required
                aria-describedby={inviteHintId}
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
              />
              <span id={inviteHintId} className="field-hint">
                {t.auth.inviteHint}
              </span>
            </label>
          )}
          {passwordsMismatch && (
            <p role="alert" className="form-error">
              {t.auth.passwordsMismatch}
            </p>
          )}
          {mutation.error && (
            <p role="alert" className="form-error">
              {isServerWaking(mutation.error) ? t.wake.retryAction : mutation.error.message}
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
        <ServerWakeNotice />
      </main>
    </div>
  )
}
