/**
 * useApi — fetch wrapper with JWT auth injection and auto-refresh.
 */
import { useCallback } from 'react'

const API_BASE = '/api'

export function getToken() {
  return localStorage.getItem('bw_access_token')
}

export function setTokens(access, refresh) {
  localStorage.setItem('bw_access_token', access)
  localStorage.setItem('bw_refresh_token', refresh)
}

export function clearTokens() {
  localStorage.removeItem('bw_access_token')
  localStorage.removeItem('bw_refresh_token')
}

// Serialize concurrent refresh attempts — only one in-flight at a time
let refreshInProgress = null

export async function refreshToken() {
  if (refreshInProgress) return refreshInProgress
  const refresh = localStorage.getItem('bw_refresh_token')
  if (!refresh) return null
  refreshInProgress = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!res.ok) { clearTokens(); return null }
      const data = await res.json()
      setTokens(data.access_token, data.refresh_token)
      return data.access_token
    } catch {
      return null
    } finally {
      refreshInProgress = null
    }
  })()
  return refreshInProgress
}

/**
 * Format an API error response body into a human-readable string.
 * Handles FastAPI's { detail: string | [{msg, loc, type}] | object } shape.
 */
export function fmtApiError(err, fallback = 'An error occurred.') {
  const detail = err?.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(d => d.msg || String(d)).join(', ')
  return fallback
}

export async function apiFetch(path, options = {}) {
  let token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  // Auto-refresh on 401
  if (res.status === 401 && token) {
    const newToken = await refreshToken()
    if (newToken) {
      headers.Authorization = `Bearer ${newToken}`
      res = await fetch(`${API_BASE}${path}`, { ...options, headers })
    }
  }

  return res
}

export function useApi() {
  const get   = useCallback((path) => apiFetch(path), [])
  const post  = useCallback((path, body) =>
    apiFetch(path, { method: 'POST',   body: JSON.stringify(body) }), [])
  const put   = useCallback((path, body) =>
    apiFetch(path, { method: 'PUT',    body: JSON.stringify(body) }), [])
  const patch = useCallback((path, body) =>
    apiFetch(path, { method: 'PATCH',  body: JSON.stringify(body) }), [])
  const del   = useCallback((path, body) =>
    apiFetch(path, { method: 'DELETE', body: body ? JSON.stringify(body) : undefined }), [])

  return { get, post, put, patch, del }
}
