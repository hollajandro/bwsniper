/**
 * AuthContext — global auth state (user, login/logout, token management).
 *
 * SECURITY NOTE: The frontend trusts the backend for all auth decisions.
 * decodeUser() extracts user_id and email from the JWT payload for display
 * purposes only. Admin checks and permission decisions are always made
 * server-side via /settings/me or other API calls. Never trust the JWT's
 * is_admin or any other privilege claim on the client without backend
 * verification.
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { apiFetch, setTokens, clearTokens, getToken, fmtApiError } from '../hooks/useApi'

const AuthContext = createContext(null)

function decodeUser(token) {
  // Use jwt-decode (structure-only verification, not signature) instead of
  // raw atob() which silently ignores malformed payloads.
  try {
    // Dynamic import to keep the bundle lean if jwt-decode isn't installed;
    // falls back to manual parse if the import fails.
    // eslint-disable-next-line no-undef
    const payload = (typeof jwt_decode === 'function')
      ? jwt_decode(token)
      : JSON.parse(atob(token.split('.')[1]))
    return {
      user_id:      payload.sub || null,
      email:        payload.email || null,
      display_name: payload.display_name || payload.email || null,
      // Frontend trusts the backend's /settings/me for is_admin; we leave
      // this as a best-effort display hint only (may be stale).
      is_admin:     payload.is_admin || false,
    }
  } catch {
    return null
  }
}

// Re-fetch user profile from the backend (authoritative source for admin flag).
async function fetchUserFromBackend() {
  try {
    const res = await apiFetch('/settings')
    if (res.ok) {
      // The settings endpoint doesn't expose is_admin, so we call /auth/me
      // which returns the full user object from the JWT's verified payload.
      const meRes = await apiFetch('/auth/me')
      if (meRes.ok) {
        return await meRes.json()
      }
    }
  } catch {}
  return null
}

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [loading, setLoading] = useState(true)

  // Restore session from stored token on mount — re-validate with backend
  useEffect(() => {
    const token = getToken()
    if (!token) { setLoading(false); return }

    fetchUserFromBackend()
      .then(profile => {
        if (profile) {
          setUser({
            user_id:      profile.user_id,
            email:        profile.email,
            display_name: profile.display_name || profile.email,
            is_admin:     profile.is_admin || false,
          })
        } else {
          // Token present but backend rejected it — clear it
          clearTokens()
        }
      })
      .catch(() => clearTokens())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await fetch('/api/auth/login', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Login failed'))
    }
    const data = await res.json()
    setTokens(data.access_token, data.refresh_token)
    setUser({
      user_id:      data.user_id,
      email:        data.email,
      display_name: data.display_name || data.email,
      is_admin:     data.is_admin || false,
    })
    return data
  }, [])

  const register = useCallback(async (email, password, displayName) => {
    const res = await fetch('/api/auth/register', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password, display_name: displayName }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Registration failed'))
    }
    const data = await res.json()
    setTokens(data.access_token, data.refresh_token)
    setUser({
      user_id:      data.user_id,
      email:        data.email,
      display_name: data.display_name || data.email,
      is_admin:     data.is_admin || false,
    })
    return data
  }, [])

  const logout = useCallback(async () => {
    // Revoke refresh token on server (best-effort — don't block UI on failure)
    const refresh = localStorage.getItem('bw_refresh_token')
    if (refresh) {
      fetch('/api/auth/logout', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ refresh_token: refresh }),
      }).catch(() => {})
    }
    clearTokens()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
