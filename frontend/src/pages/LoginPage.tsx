import { useState, type FormEvent } from 'react'
import { useLogin, useRegister } from '../hooks/useAuth'

type Mode = 'login' | 'register'

export function LoginPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const loginMutation = useLogin()
  const registerMutation = useRegister()
  const mutation = mode === 'login' ? loginMutation : registerMutation

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
    <main>
      <h1>MyStocks</h1>
      <h2>{mode === 'login' ? 'Log in' : 'Create account'}</h2>
      <form onSubmit={handleSubmit} className="auth-form">
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            minLength={mode === 'register' ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === 'register' && (
          <label>
            Confirm password
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
        {passwordsMismatch && <p role="alert">Passwords don't match</p>}
        {mutation.error && <p role="alert">{mutation.error.message}</p>}
        <button
          type="submit"
          disabled={mutation.isPending || (mode === 'register' && passwordsMismatch)}
        >
          {mode === 'login' ? 'Log in' : 'Register'}
        </button>
      </form>
      <button type="button" className="link-button" onClick={toggleMode}>
        {mode === 'login' ? 'Need an account? Register' : 'Have an account? Log in'}
      </button>
    </main>
  )
}
