import { describe, expect, it, vi } from 'vitest'
import { apiFetch, refreshToken } from './useApi'

function jsonResponse(body, init = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: vi.fn().mockResolvedValue(body),
  }
}

describe('useApi auth flow', () => {
  it('serializes concurrent refresh requests', async () => {
    localStorage.setItem('bw_refresh_token', 'refresh-token')

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ access_token: 'new-access', refresh_token: 'new-refresh' })
    )
    vi.stubGlobal('fetch', fetchMock)

    const [first, second] = await Promise.all([refreshToken(), refreshToken()])

    expect(first).toBe('new-access')
    expect(second).toBe('new-access')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/refresh', expect.objectContaining({
      method: 'POST',
    }))
    expect(localStorage.getItem('bw_access_token')).toBe('new-access')
    expect(localStorage.getItem('bw_refresh_token')).toBe('new-refresh')
  })

  it('retries API requests with a refreshed access token after a 401', async () => {
    localStorage.setItem('bw_access_token', 'expired-access')
    localStorage.setItem('bw_refresh_token', 'refresh-token')

    const authHeaders = []
    const fetchMock = vi.fn(async (url, options) => {
      authHeaders.push(options?.headers?.Authorization ?? null)

      if (url === '/api/snipes' && authHeaders.length === 1) {
        return { status: 401, ok: false }
      }
      if (url === '/api/auth/refresh') {
        return jsonResponse({ access_token: 'fresh-access', refresh_token: 'fresh-refresh' })
      }
      return { status: 200, ok: true }
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiFetch('/snipes')

    expect(result.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/snipes')
    expect(fetchMock.mock.calls[2][0]).toBe('/api/snipes')
    expect(authHeaders).toEqual([
      'Bearer expired-access',
      null,
      'Bearer fresh-access',
    ])
    expect(localStorage.getItem('bw_access_token')).toBe('fresh-access')
    expect(localStorage.getItem('bw_refresh_token')).toBe('fresh-refresh')
  })
})
