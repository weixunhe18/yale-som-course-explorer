import { useState } from 'react'
import { login, signup } from '../api'

type Props = {
  /** Called with the username once the token is stored. */
  onSignedIn: (username: string) => void
}

type Mode = 'login' | 'signup'

export default function Login({ onSignedIn }: Props) {
  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const signingUp = mode === 'signup'

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      const fn = signingUp ? signup : login
      const result = await fn(username.trim(), password)
      onSignedIn(result.username)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  function swap(next: Mode) {
    setMode(next)
    setError('')
  }

  return (
    <div className="gate">
      <form className="gate__card" onSubmit={submit}>
        <span className="bell gate__bell" aria-hidden="true" />
        <h1 className="gate__title">Yale SOM Course Explorer</h1>
        <p className="gate__sub">
          {signingUp
            ? 'Create an account to save your chats.'
            : 'Sign in to pick up where you left off.'}
        </p>

        <div className="gate__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={!signingUp}
            className={`gate__tab${!signingUp ? ' gate__tab--on' : ''}`}
            onClick={() => swap('login')}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={signingUp}
            className={`gate__tab${signingUp ? ' gate__tab--on' : ''}`}
            onClick={() => swap('signup')}
          >
            Create account
          </button>
        </div>

        <label className="gate__label" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          className="gate__input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="3–32 characters"
          required
          disabled={busy}
        />

        <label className="gate__label" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          className="gate__input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          // Tells the browser's password manager whether to offer a saved
          // password or to generate a new one.
          autoComplete={signingUp ? 'new-password' : 'current-password'}
          placeholder={signingUp ? 'At least 8 characters' : '••••••••'}
          required
          disabled={busy}
        />

        {error && (
          <p className="gate__error" role="alert">
            {error}
          </p>
        )}

        <button
          className="gate__submit"
          type="submit"
          disabled={busy || !username.trim() || !password}
        >
          {busy ? 'One moment…' : signingUp ? 'Create account' : 'Sign in'}
        </button>

        <p className="gate__foot">
          {signingUp ? 'Already have an account?' : 'New here?'}{' '}
          <button
            type="button"
            className="linkish"
            onClick={() => swap(signingUp ? 'login' : 'signup')}
          >
            {signingUp ? 'Sign in' : 'Create one'}
          </button>
        </p>
      </form>
    </div>
  )
}
