import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = {
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}

const me = {
  user_id: 'me-user',
  email: 'me@example.com',
  display_name: 'Me',
  is_admin: true,
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: me }),
}))

vi.mock('../hooks/useApi', () => ({
  useApi: () => api,
  fmtApiError: (err, fallback = 'An error occurred.') => {
    const detail = err?.detail
    if (!detail) return fallback
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => item.msg || String(item)).join(', ')
    return fallback
  },
}))

import Admin from './Admin'

function response(body, init = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: vi.fn().mockResolvedValue(body),
  }
}

function buildUsers() {
  return [
    {
      id: 'me-user',
      email: 'me@example.com',
      display_name: 'Me',
      is_admin: true,
      remote_redundancy_enabled: false,
      remote_agent_id: null,
      created_at: '2026-04-20T10:00:00.000Z',
    },
    {
      id: 'user-2',
      email: 'target@example.com',
      display_name: 'Target',
      is_admin: false,
      remote_redundancy_enabled: false,
      remote_agent_id: null,
      created_at: '2026-04-21T10:00:00.000Z',
    },
  ]
}

function buildAgents() {
  return [
    {
      id: 'agent-1',
      name: 'West Agent',
      region: 'us-west-1',
      enabled: true,
      last_seen_at: '2026-04-23T10:00:00.000Z',
      last_error: null,
      clock_offset_ms: 8,
      created_at: '2026-04-23T09:00:00.000Z',
      updated_at: '2026-04-23T10:00:00.000Z',
    },
    {
      id: 'agent-2',
      name: 'East Agent',
      region: 'us-east-1',
      enabled: false,
      last_seen_at: null,
      last_error: 'Lost backend connectivity',
      clock_offset_ms: null,
      created_at: '2026-04-23T09:05:00.000Z',
      updated_at: '2026-04-23T10:05:00.000Z',
    },
  ]
}

async function renderAdmin({ users = buildUsers(), agents = buildAgents() } = {}) {
  api.get.mockImplementation(async (path) => {
    if (path === '/admin/users') return response(users)
    if (path === '/admin/remote-agents') return response(agents)
    throw new Error(`Unhandled GET ${path}`)
  })
  api.post.mockReset()
  api.patch.mockReset()
  api.del.mockReset()

  render(<Admin />)

  await screen.findByText('Remote Agents')
  await screen.findByText('Users')
}

describe('Admin remote redundancy UI', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.post.mockReset()
    api.patch.mockReset()
    api.del.mockReset()
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it('loads users and remote agents in parallel', async () => {
    await renderAdmin()

    expect(api.get).toHaveBeenCalledWith('/admin/users')
    expect(api.get).toHaveBeenCalledWith('/admin/remote-agents')
    expect(await screen.findByText('West Agent')).not.toBeNull()
    expect(await screen.findByText('Target')).not.toBeNull()
  })

  it('creates a remote agent and shows the one-time key modal', async () => {
    await renderAdmin()

    api.post.mockResolvedValueOnce(
      response({
        id: 'agent-3',
        name: 'Backup Agent',
        region: 'eu-central-1',
        enabled: true,
        last_seen_at: null,
        last_error: null,
        clock_offset_ms: null,
        created_at: '2026-04-23T11:00:00.000Z',
        updated_at: '2026-04-23T11:00:00.000Z',
        api_key: 'super-secret-agent-key',
      })
    )

    fireEvent.click(screen.getByRole('button', { name: /\+ Create Agent/i }))

    fireEvent.change(screen.getByPlaceholderText('Agent name'), {
      target: { value: 'Backup Agent' },
    })
    fireEvent.change(screen.getByPlaceholderText('Region \(optional\)'), {
      target: { value: 'eu-central-1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create Agent' }))

    await screen.findByText('Remote Agent API Key')
    expect(api.post).toHaveBeenCalledWith('/admin/remote-agents', {
      name: 'Backup Agent',
      region: 'eu-central-1',
      enabled: true,
    })
    expect(screen.getByText('super-secret-agent-key')).not.toBeNull()
    expect(screen.getAllByText((content) => content.includes('****'))[0]).not.toBeNull()
  })

  it('rotates a key through confirmation and shows the replacement key once', async () => {
    await renderAdmin()

    api.patch.mockResolvedValueOnce(
      response({
        id: 'agent-1',
        name: 'West Agent',
        region: 'us-west-1',
        enabled: true,
        last_seen_at: '2026-04-23T10:00:00.000Z',
        last_error: null,
        clock_offset_ms: 8,
        created_at: '2026-04-23T09:00:00.000Z',
        updated_at: '2026-04-23T11:00:00.000Z',
        api_key: 'rotated-key-123',
      })
    )

    const westRow = screen.getByText('West Agent').closest('tr')
    fireEvent.click(within(westRow).getByRole('button', { name: 'Rotate Key' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rotate Key' }))

    await screen.findByText('rotated-key-123')
    expect(api.patch).toHaveBeenCalledWith('/admin/remote-agents/agent-1', {
      rotate_api_key: true,
    })
  })

  it('toggles a remote agent enabled state', async () => {
    await renderAdmin()

    api.patch.mockResolvedValueOnce(
      response({
        ...buildAgents()[0],
        enabled: false,
      })
    )

    const westRow = screen.getByText('West Agent').closest('tr')
    fireEvent.click(within(westRow).getByRole('button', { name: 'Disable' }))

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith('/admin/remote-agents/agent-1', {
        enabled: false,
      })
    })
    await waitFor(() => {
      const updatedWestRow = screen.getByText('West Agent').closest('tr')
      expect(within(updatedWestRow).getByRole('button', { name: 'Enable' })).not.toBeNull()
    })
  })

  it('patches user agent assignment immediately on select change', async () => {
    await renderAdmin()

    api.patch.mockResolvedValueOnce(
      response({
        ...buildUsers()[1],
        remote_agent_id: 'agent-1',
      })
    )

    const userRow = screen.getByText('Target').closest('tr')
    fireEvent.change(within(userRow).getByRole('combobox'), {
      target: { value: 'agent-1' },
    })

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith('/admin/users/user-2', {
        remote_agent_id: 'agent-1',
      })
    })
    expect(within(userRow).getByRole('combobox').value).toBe('agent-1')
  })

  it('blocks enabling redundancy when no remote agent is selected', async () => {
    await renderAdmin()

    const userRow = screen.getByText('Target').closest('tr')
    const select = within(userRow).getByRole('combobox')
    fireEvent.click(within(userRow).getByRole('button', { name: 'Enable' }))

    expect((await screen.findAllByText('Select a remote agent before enabling redundancy.')).length).toBeGreaterThan(0)
    expect(api.patch).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(select)
  })

  it('enables and disables user redundancy while preserving agent assignment', async () => {
    await renderAdmin({
      users: [
        buildUsers()[0],
        {
          ...buildUsers()[1],
          remote_agent_id: 'agent-1',
          remote_redundancy_enabled: false,
        },
      ],
    })

    api.patch
      .mockResolvedValueOnce(
        response({
          ...buildUsers()[1],
          remote_agent_id: 'agent-1',
          remote_redundancy_enabled: true,
        })
      )
      .mockResolvedValueOnce(
        response({
          ...buildUsers()[1],
          remote_agent_id: 'agent-1',
          remote_redundancy_enabled: false,
        })
      )

    const userRow = screen.getByText('Target').closest('tr')

    fireEvent.click(within(userRow).getByRole('button', { name: 'Enable' }))
    await waitFor(() => {
      expect(api.patch).toHaveBeenNthCalledWith(1, '/admin/users/user-2', {
        remote_redundancy_enabled: true,
        remote_agent_id: 'agent-1',
      })
    })
    await waitFor(() => {
      const updatedUserRow = screen.getByText('Target').closest('tr')
      expect(within(updatedUserRow).getByRole('button', { name: 'Disable' })).not.toBeNull()
    })

    fireEvent.click(within(screen.getByText('Target').closest('tr')).getByRole('button', { name: 'Disable' }))
    await waitFor(() => {
      expect(api.patch).toHaveBeenNthCalledWith(2, '/admin/users/user-2', {
        remote_redundancy_enabled: false,
      })
    })
    expect(within(userRow).getByRole('combobox').value).toBe('agent-1')
  })

  it('keeps admin role toggles working', async () => {
    await renderAdmin()

    api.patch.mockResolvedValueOnce(
      response({
        ...buildUsers()[1],
        is_admin: true,
      })
    )

    const userRow = screen.getByText('Target').closest('tr')
    fireEvent.click(within(userRow).getByRole('button', { name: 'Make Admin' }))

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith('/admin/users/user-2', {
        is_admin: true,
      })
    })
    await waitFor(() => {
      const updatedUserRow = screen.getByText('Target').closest('tr')
      expect(within(updatedUserRow).getByRole('button', { name: 'Remove Admin' })).not.toBeNull()
    })
  })

  it('keeps password reset working', async () => {
    await renderAdmin()

    api.post.mockResolvedValueOnce(response({}))

    const userRow = screen.getByText('Target').closest('tr')
    fireEvent.click(within(userRow).getByRole('button', { name: 'Reset Password' }))

    fireEvent.change(screen.getByPlaceholderText('New password'), {
      target: { value: 'newpassword123' },
    })
    fireEvent.change(screen.getByPlaceholderText('Confirm password'), {
      target: { value: 'newpassword123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/admin/users/user-2/reset-password', {
        new_password: 'newpassword123',
      })
    })
  })

  it('keeps user deletion working', async () => {
    await renderAdmin()

    api.del.mockResolvedValueOnce(response({}))

    const userRow = screen.getByText('Target').closest('tr')
    fireEvent.click(within(userRow).getByRole('button', { name: 'Delete' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(api.del).toHaveBeenCalledWith('/admin/users/user-2')
    })
    await waitFor(() => {
      expect(screen.queryByText('Target')).toBeNull()
    })
  })
})
