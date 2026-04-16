import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login, register } = useAuth()
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await register(email, password, displayName || undefined)
      } else {
        await login(email, password)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        {/* Logo mark */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-bw-blue flex items-center justify-center text-white text-xl font-bold shadow-mat-2 mb-4">
            BW
          </div>
          <h1 className="text-2xl font-semibold text-white tracking-tight">BW Sniper</h1>
          <p className="text-sm text-gray-500 mt-1">
            {isRegister ? 'Create your account' : 'Sign in to continue'}
          </p>
        </div>

        {/* Card */}
        <div className="card p-6 space-y-4">
          <form onSubmit={handleSubmit} className="space-y-3">
            {isRegister && (
              <div>
                <label htmlFor="display-name" className="sr-only">Display name</label>
                <input
                  id="display-name"
                  type="text"
                  placeholder="Display name (optional)"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  className="field"
                />
              </div>
            )}
            <div>
              <label htmlFor="email" className="sr-only">Email</label>
              <input
                id="email"
                type="email"
                placeholder="Email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="field"
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">Password</label>
              <input
                id="password"
                type="password"
                placeholder="Password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={6}
                className="field"
              />
            </div>
            {error && (
              <p className="text-bw-red text-xs bg-bw-red/10 border border-bw-red/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full mt-1">
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Please wait…
                </span>
              ) : (
                isRegister ? 'Create Account' : 'Sign In'
              )}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-sm text-gray-500">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}
          {' '}
          <button
            onClick={() => { setIsRegister(!isRegister); setError('') }}
            className="text-bw-blue hover:text-bw-blue/80 font-medium transition-colors"
          >
            {isRegister ? 'Sign In' : 'Register'}
          </button>
        </p>
      </div>
    </div>
  )
}
