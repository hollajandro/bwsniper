import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Browse from './Browse'

const api = { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }

vi.mock('../hooks/useApi', async importOriginal => ({
  ...await importOriginal(),
  useApi: () => api,
}))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { user_id: 'user-1' } }) }))
vi.mock('../hooks/useWebSocket', () => ({ useWebSocket: () => {} }))

function response(body, ok = true) {
  return { ok, status: ok ? 200 : 502, json: async () => body }
}

function auction(id, title) {
  return { id, item: { title }, endDate: new Date(Date.now() + 86400000).toISOString() }
}

const saved = auction('saved-1', 'Locally watched item')
const catalog = auction('catalog-1', 'Unwatched catalog item')

function renderBrowse() {
  render(<MemoryRouter><Browse /></MemoryRouter>)
}

beforeEach(() => {
  api.post.mockReset()
  api.get.mockImplementation(async path => {
    if (path === '/logins') return response([{ id: 'login-1', display_name: 'Test account' }])
    if (path === '/watchlist') return response([{ id: 'watch-1', auction_id: saved.id, snapshot: saved }])
    if (path === '/settings') return response({})
    if (path.startsWith('/snipes?') || path.startsWith('/auctions/locations/list?')) return response([])
    throw new Error(`Unexpected request: ${path}`)
  })
  vi.stubGlobal('IntersectionObserver', class {
    observe() {}
    disconnect() {}
  })
})

describe('Watched quick filter', () => {
  it('does not classify the catalog as watched when the watched request fails', async () => {
    api.post.mockImplementation(async (_path, body) => body.watching
      ? response({ detail: 'BuyWander session could not be refreshed.' }, false)
      : response({ items: [saved, catalog], hasNextPage: false }))
    renderBrowse()
    await screen.findByText(catalog.item.title)

    fireEvent.click(screen.getByRole('button', { name: 'Watched', exact: true }))

    expect((await screen.findByRole('alert')).textContent).toContain('session could not be refreshed')
    await screen.findByText(saved.item.title)
    expect(screen.queryByText(catalog.item.title)).toBeNull()
  })

  it('keeps watched results when an older catalog page finishes afterwards', async () => {
    let finishOldPage
    const oldPage = new Promise(resolve => { finishOldPage = resolve })
    const upstream = auction('upstream-1', 'Watched on BuyWander')
    api.post.mockImplementation(async (_path, body) => {
      if (body.watching) return response({ items: [upstream], hasNextPage: false })
      if (body.page > 1) return oldPage
      return response({ items: [catalog], hasNextPage: true })
    })
    renderBrowse()
    await screen.findByText(catalog.item.title)
    await waitFor(() => expect(api.post.mock.calls.some(([, body]) => body.page === 2)).toBe(true))

    fireEvent.click(screen.getByRole('button', { name: 'Watched', exact: true }))
    await screen.findByText(upstream.item.title)
    await act(async () => { finishOldPage(response({ items: [catalog], hasNextPage: false })) })

    expect(screen.queryByText(catalog.item.title)).toBeNull()
    expect(screen.getByText(upstream.item.title)).toBeTruthy()
    expect(screen.getByText(saved.item.title)).toBeTruthy()
  })

  it('shows an empty result when neither watchlist has items', async () => {
    const originalGet = api.get.getMockImplementation()
    api.get.mockImplementation(path => path === '/watchlist' ? Promise.resolve(response([])) : originalGet(path))
    api.post.mockImplementation(async (_path, body) => response({
      items: body.watching ? [] : [catalog], hasNextPage: false,
    }))
    renderBrowse()
    await screen.findByText(catalog.item.title)

    fireEvent.click(screen.getByRole('button', { name: 'Watched', exact: true }))

    await screen.findByText('No auctions found. Try adjusting your filters.')
    expect(screen.queryByText(catalog.item.title)).toBeNull()
  })
})
