import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { useApi, fmtApiError } from '../hooks/useApi'

function ErrorBanner({ message, onDismiss }) {
  if (!message) return null

  return (
    <div className="bg-bw-red/10 border border-bw-red/30 rounded-lg px-4 py-3 text-sm text-bw-red flex items-center justify-between">
      <span>{message}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="text-bw-red hover:text-bw-red/70 ml-4"
      >
        x
      </button>
    </div>
  )
}

function CreateUserModal({ onClose, onSave }) {
  const [form, setForm] = useState({
    email: '',
    password: '',
    display_name: '',
    is_admin: false,
  })
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const set = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (form.password !== confirm) {
      setError('Passwords do not match')
      return
    }
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setSaving(true)
    try {
      await onSave(form)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to create user')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="card w-full max-w-sm mx-4 p-6">
        <h3 className="text-base font-semibold text-white mb-4">Create User</h3>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="email"
            placeholder="Email address"
            value={form.email}
            onChange={(e) => set('email', e.target.value)}
            className="field w-full"
            autoFocus
            required
          />
          <input
            type="text"
            placeholder="Display name (optional)"
            value={form.display_name}
            onChange={(e) => set('display_name', e.target.value)}
            className="field w-full"
          />
          <input
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={(e) => set('password', e.target.value)}
            className="field w-full"
            required
          />
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => {
              setConfirm(e.target.value)
              setError('')
            }}
            className="field w-full"
            required
          />
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={form.is_admin}
              onChange={(e) => set('is_admin', e.target.checked)}
              className="rounded"
            />
            Grant admin privileges
          </label>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="btn btn-primary flex-1">
              {saving ? 'Creating...' : 'Create User'}
            </button>
            <button type="button" onClick={onClose} className="btn btn-secondary flex-1">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ResetPasswordModal({ user, onClose, onSave }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setSaving(true)
    try {
      await onSave(password)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to reset password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="card w-full max-w-sm mx-4 p-6">
        <h3 className="text-base font-semibold text-white mb-1">Reset Password</h3>
        <p className="text-xs text-gray-400 mb-4">
          Set a new password for <span className="text-gray-200">{user.email}</span>
        </p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            placeholder="New password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              setError('')
            }}
            className="field w-full"
            autoFocus
          />
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => {
              setConfirm(e.target.value)
              setError('')
            }}
            className="field w-full"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="btn btn-primary flex-1">
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button type="button" onClick={onClose} className="btn btn-secondary flex-1">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function CreateRemoteAgentModal({ onClose, onSave }) {
  const [form, setForm] = useState({
    name: '',
    region: '',
    enabled: true,
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const set = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setError('Agent name is required')
      return
    }

    setSaving(true)
    try {
      await onSave({
        name: form.name.trim(),
        region: form.region.trim() || null,
        enabled: form.enabled,
      })
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to create agent')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="card w-full max-w-sm mx-4 p-6">
        <h3 className="text-base font-semibold text-white mb-4">Create Remote Agent</h3>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Agent name"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            className="field w-full"
            autoFocus
            required
          />
          <input
            type="text"
            placeholder="Region (optional)"
            value={form.region}
            onChange={(e) => set('region', e.target.value)}
            className="field w-full"
          />
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => set('enabled', e.target.checked)}
              className="rounded"
            />
            Enable this agent immediately
          </label>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="btn btn-primary flex-1">
              {saving ? 'Creating...' : 'Create Agent'}
            </button>
            <button type="button" onClick={onClose} className="btn btn-secondary flex-1">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ApiKeyModal({ agentName, apiKey, onClose }) {
  const [copyStatus, setCopyStatus] = useState('')

  const handleCopy = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(apiKey)
      }
      setCopyStatus('Copied')
    } catch {
      setCopyStatus('Copy failed')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="card w-full max-w-lg mx-4 p-6">
        <h3 className="text-base font-semibold text-white mb-1">Remote Agent API Key</h3>
        <p className="text-sm text-gray-300 mb-4">
          Save this key for <span className="text-white font-medium">{agentName}</span>. It
          will not be shown again after you close this dialog.
        </p>
        <div className="rounded-lg border border-gray-700 bg-gray-950/80 p-3 mb-4">
          <code className="block break-all text-sm text-bw-blue">{apiKey}</code>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-xs text-gray-500">
            Use this as <code className="text-gray-300">REMOTE_AGENT_API_KEY</code> on the
            remote host.
          </span>
          <div className="flex gap-2 shrink-0">
            <button onClick={handleCopy} className="btn btn-secondary">
              {copyStatus === 'Copied' ? 'Copied' : 'Copy Key'}
            </button>
            <button onClick={onClose} className="btn btn-primary">
              Done
            </button>
          </div>
        </div>
        {copyStatus === 'Copy failed' && (
          <p className="mt-3 text-xs text-red-400">Clipboard access failed. Copy the key manually.</p>
        )}
      </div>
    </div>
  )
}

function ConfirmDialog({ title, message, confirmLabel, confirmClassName, onCancel, onConfirm }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="card w-full max-w-sm mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-dialog-title" className="text-base font-semibold text-white mb-3">
          {title}
        </h3>
        <p className="text-sm text-gray-300 mb-5">{message}</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="btn btn-secondary">
            Cancel
          </button>
          <button onClick={onConfirm} className={confirmClassName}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function LoadingPanel() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-6 h-6 rounded-full border-2 border-bw-blue border-t-transparent animate-spin" />
    </div>
  )
}

function sanitizeAgent(agent) {
  if (!agent) return null
  const { api_key: _apiKey, ...rest } = agent
  return rest
}

function sortUsers(users) {
  return [...users].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
}

function sortAgents(agents) {
  return [...agents].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
}

function formatDate(value) {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

function getAgentHealth(agent) {
  if (!agent.enabled) {
    return {
      label: 'Disabled',
      className: 'bg-gray-700/50 text-gray-400 border-gray-600/30',
    }
  }
  if (agent.last_error) {
    return {
      label: 'Error',
      className: 'bg-bw-red/10 text-bw-red border-bw-red/30',
    }
  }
  if (!agent.last_seen_at) {
    return {
      label: 'Waiting',
      className: 'bg-amber-400/10 text-amber-300 border-amber-300/30',
    }
  }
  const ageMs = Date.now() - new Date(agent.last_seen_at).getTime()
  if (ageMs > 60000) {
    return {
      label: 'Stale',
      className: 'bg-amber-400/10 text-amber-300 border-amber-300/30',
    }
  }
  return {
    label: 'Healthy',
    className: 'bg-emerald-400/10 text-emerald-300 border-emerald-300/30',
  }
}

export default function Admin() {
  const { user: me } = useAuth()
  const { get, post, patch, del } = useApi()

  const [users, setUsers] = useState([])
  const [agents, setAgents] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(true)
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [userError, setUserError] = useState('')
  const [agentError, setAgentError] = useState('')
  const [actionError, setActionError] = useState('')
  const [resetTarget, setResetTarget] = useState(null)
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [showCreateAgent, setShowCreateAgent] = useState(false)
  const [keyModal, setKeyModal] = useState(null)
  const [toast, setToast] = useState('')
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [busyUsers, setBusyUsers] = useState({})
  const [busyAgents, setBusyAgents] = useState({})

  const toastTimerRef = useRef(null)
  const userAgentSelectRefs = useRef({})

  const showToast = useCallback((message) => {
    setToast(message)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(''), 3000)
  }, [])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    }
  }, [])

  const agentOptions = useMemo(() => sortAgents(agents), [agents])

  const replaceUser = useCallback((nextUser) => {
    setUsers((prev) =>
      sortUsers(prev.map((user) => (user.id === nextUser.id ? nextUser : user)))
    )
  }, [])

  const replaceAgent = useCallback((nextAgent) => {
    const safeAgent = sanitizeAgent(nextAgent)
    setAgents((prev) =>
      sortAgents(prev.map((agent) => (agent.id === safeAgent.id ? safeAgent : agent)))
    )
  }, [])

  const fetchUsers = useCallback(async () => {
    setLoadingUsers(true)
    setUserError('')
    try {
      const res = await get('/admin/users')
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(fmtApiError(err, 'Failed to load users'))
      }
      setUsers(sortUsers(await res.json()))
    } catch (err) {
      setUserError(err.message || 'Failed to load users')
    } finally {
      setLoadingUsers(false)
    }
  }, [get])

  const fetchAgents = useCallback(async () => {
    setLoadingAgents(true)
    setAgentError('')
    try {
      const res = await get('/admin/remote-agents')
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(fmtApiError(err, 'Failed to load remote agents'))
      }
      setAgents(sortAgents((await res.json()).map(sanitizeAgent)))
    } catch (err) {
      setAgentError(err.message || 'Failed to load remote agents')
    } finally {
      setLoadingAgents(false)
    }
  }, [get])

  const refreshAll = useCallback(() => {
    setActionError('')
    fetchUsers()
    fetchAgents()
  }, [fetchAgents, fetchUsers])

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  const setUserBusy = useCallback((userId, value) => {
    setBusyUsers((prev) => ({ ...prev, [userId]: value }))
  }, [])

  const setAgentBusy = useCallback((agentId, value) => {
    setBusyAgents((prev) => ({ ...prev, [agentId]: value }))
  }, [])

  const patchUserRecord = useCallback(
    async (userId, body, fallback) => {
      const res = await patch(`/admin/users/${userId}`, body)
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(fmtApiError(err, fallback))
      }
      const updated = await res.json()
      replaceUser(updated)
      return updated
    },
    [patch, replaceUser]
  )

  const createUser = async (form) => {
    const res = await post('/admin/users', form)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Create failed'))
    }
    const newUser = await res.json()
    setUsers((prev) => sortUsers([...prev, newUser]))
    showToast(`Created user ${newUser.email}`)
  }

  const toggleAdmin = async (user) => {
    setActionError('')
    setUserBusy(user.id, true)
    try {
      const updated = await patchUserRecord(
        user.id,
        { is_admin: !user.is_admin },
        'Update failed'
      )
      showToast(
        `${updated.email} is ${updated.is_admin ? 'now an admin' : 'no longer an admin'}`
      )
    } catch (err) {
      setActionError(err.message)
    } finally {
      setUserBusy(user.id, false)
    }
  }

  const resetPassword = async (user, newPassword) => {
    const res = await post(`/admin/users/${user.id}/reset-password`, {
      new_password: newPassword,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Reset failed'))
    }
    showToast(`Password reset for ${user.email}`)
  }

  const confirmDeleteUser = (user) => {
    setConfirmDialog({
      title: 'Confirm Delete',
      message: `Delete ${user.email} and all their data? This cannot be undone.`,
      confirmLabel: 'Delete',
      confirmClassName: 'btn btn-danger',
      onConfirm: async () => {
        setConfirmDialog(null)
        setActionError('')
        setUserBusy(user.id, true)
        try {
          const res = await del(`/admin/users/${user.id}`)
          if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(fmtApiError(err, 'Delete failed'))
          }
          setUsers((prev) => prev.filter((entry) => entry.id !== user.id))
          showToast(`Deleted ${user.email}`)
        } catch (err) {
          setActionError(err.message)
        } finally {
          setUserBusy(user.id, false)
        }
      },
    })
  }

  const createAgent = async (form) => {
    const res = await post('/admin/remote-agents', form)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Create failed'))
    }
    const created = await res.json()
    setAgents((prev) => sortAgents([...prev, sanitizeAgent(created)]))
    if (created.api_key) {
      setKeyModal({ agentName: created.name, apiKey: created.api_key })
    }
    showToast(`Created remote agent ${created.name}`)
  }

  const updateAgent = useCallback(
    async (agentId, body, fallback) => {
      const res = await patch(`/admin/remote-agents/${agentId}`, body)
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(fmtApiError(err, fallback))
      }
      const updated = await res.json()
      replaceAgent(updated)
      return updated
    },
    [patch, replaceAgent]
  )

  const toggleAgentEnabled = async (agent) => {
    setActionError('')
    setAgentBusy(agent.id, true)
    try {
      const updated = await updateAgent(
        agent.id,
        { enabled: !agent.enabled },
        'Failed to update agent'
      )
      showToast(`${updated.name} ${updated.enabled ? 'enabled' : 'disabled'}`)
    } catch (err) {
      setActionError(err.message)
    } finally {
      setAgentBusy(agent.id, false)
    }
  }

  const confirmRotateAgentKey = (agent) => {
    setConfirmDialog({
      title: 'Rotate API Key',
      message: `Rotate the API key for ${agent.name}? The current deployed agent will stop syncing until its environment is updated.`,
      confirmLabel: 'Rotate Key',
      confirmClassName: 'btn btn-primary',
      onConfirm: async () => {
        setConfirmDialog(null)
        setActionError('')
        setAgentBusy(agent.id, true)
        try {
          const updated = await updateAgent(
            agent.id,
            { rotate_api_key: true },
            'Failed to rotate API key'
          )
          if (updated.api_key) {
            setKeyModal({ agentName: updated.name, apiKey: updated.api_key })
          }
          showToast(`Rotated API key for ${updated.name}`)
        } catch (err) {
          setActionError(err.message)
        } finally {
          setAgentBusy(agent.id, false)
        }
      },
    })
  }

  const handleUserAgentChange = async (user, nextAgentId) => {
    if (!nextAgentId || nextAgentId === user.remote_agent_id) return

    setActionError('')
    setUserBusy(user.id, true)
    try {
      const updated = await patchUserRecord(
        user.id,
        { remote_agent_id: nextAgentId },
        'Failed to update remote agent assignment'
      )
      showToast(`Assigned ${updated.email} to remote agent`)
    } catch (err) {
      setActionError(err.message)
    } finally {
      setUserBusy(user.id, false)
    }
  }

  const handleRedundancyToggle = async (user) => {
    if (!user.remote_redundancy_enabled && !user.remote_agent_id) {
      setActionError('Select a remote agent before enabling redundancy.')
      showToast('Select a remote agent before enabling redundancy.')
      userAgentSelectRefs.current[user.id]?.focus()
      return
    }

    setActionError('')
    setUserBusy(user.id, true)
    try {
      const updated = await patchUserRecord(
        user.id,
        {
          remote_redundancy_enabled: !user.remote_redundancy_enabled,
          ...(user.remote_redundancy_enabled
            ? {}
            : { remote_agent_id: user.remote_agent_id }),
        },
        'Failed to update redundancy'
      )
      showToast(
        `${updated.email} redundancy ${updated.remote_redundancy_enabled ? 'enabled' : 'disabled'}`
      )
    } catch (err) {
      setActionError(err.message)
    } finally {
      setUserBusy(user.id, false)
    }
  }

  const noAgentsAvailable = !loadingAgents && agentOptions.length === 0

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-white">User Administration</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Manage admin access, remote redundancy, and remote agents in one place.
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowCreateUser(true)} className="btn btn-primary text-xs">
              + Create User
            </button>
            <button onClick={refreshAll} className="btn btn-secondary text-xs">
              Refresh
            </button>
          </div>
        </div>

        <ErrorBanner message={actionError} onDismiss={() => setActionError('')} />
        <ErrorBanner message={agentError} onDismiss={() => setAgentError('')} />
        <ErrorBanner message={userError} onDismiss={() => setUserError('')} />

        <div className="card overflow-hidden p-0">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
            <div>
              <h2 className="text-lg font-semibold text-white">Remote Agents</h2>
              <p className="text-sm text-gray-400 mt-0.5">
                Provision remote execution nodes and monitor their sync health.
              </p>
            </div>
            <button onClick={() => setShowCreateAgent(true)} className="btn btn-primary text-xs">
              + Create Agent
            </button>
          </div>

          {loadingAgents ? (
            <LoadingPanel />
          ) : agentOptions.length === 0 ? (
            <div className="px-6 py-8 text-sm text-gray-400">
              No remote agents have been created yet. Create one before enabling redundancy on a user account.
            </div>
          ) : (
            <table className="mat-table w-full">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Health</th>
                  <th>Last Seen</th>
                  <th>Clock Skew</th>
                  <th>Last Error</th>
                  <th>API Key</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {agentOptions.map((agent) => {
                  const health = getAgentHealth(agent)
                  const busy = Boolean(busyAgents[agent.id])

                  return (
                    <tr key={agent.id}>
                      <td>
                        <div className="flex flex-col">
                          <span className="text-sm text-white font-medium">{agent.name}</span>
                          <span className="text-xs text-gray-500">
                            {agent.region || 'Region not set'}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="flex flex-col gap-1">
                          <span className={`badge text-xs ${health.className}`}>{health.label}</span>
                          <span className={`badge text-xs ${agent.enabled ? 'bg-bw-blue/20 text-bw-blue border-bw-blue/30' : 'bg-gray-700/50 text-gray-400 border-gray-600/30'}`}>
                            {agent.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </div>
                      </td>
                      <td className="text-xs text-gray-400">{formatDate(agent.last_seen_at)}</td>
                      <td className="text-xs text-gray-400">
                        {agent.clock_offset_ms == null ? '-' : `${agent.clock_offset_ms} ms`}
                      </td>
                      <td>
                        <span className="text-xs text-gray-400">
                          {agent.last_error || 'No recent errors'}
                        </span>
                      </td>
                      <td>
                        <code className="text-xs text-gray-500">****************</code>
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => toggleAgentEnabled(agent)}
                            disabled={busy}
                            className="btn btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            {agent.enabled ? 'Disable' : 'Enable'}
                          </button>
                          <button
                            onClick={() => confirmRotateAgentKey(agent)}
                            disabled={busy}
                            className="btn btn-secondary text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            Rotate Key
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {noAgentsAvailable && (
          <div className="rounded-lg border border-amber-300/20 bg-amber-300/8 px-4 py-3 text-sm text-amber-200">
            Remote redundancy cannot be enabled until at least one remote agent exists.
          </div>
        )}

        <div className="card overflow-hidden p-0">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
            <div>
              <h2 className="text-lg font-semibold text-white">Users</h2>
              <p className="text-sm text-gray-400 mt-0.5">
                {users.length} registered user{users.length !== 1 ? 's' : ''}
              </p>
            </div>
          </div>

          {loadingUsers ? (
            <LoadingPanel />
          ) : (
            <table className="mat-table w-full">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Remote Agent</th>
                  <th>Redundancy</th>
                  <th>Joined</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const busy = Boolean(busyUsers[user.id])

                  return (
                    <tr key={user.id}>
                      <td>
                        <div className="flex flex-col">
                          <span className="text-sm text-white font-medium">
                            {user.display_name || user.email}
                            {user.id === me?.user_id && (
                              <span className="ml-2 text-xs text-bw-blue font-normal">(you)</span>
                            )}
                          </span>
                          {user.display_name && (
                            <span className="text-xs text-gray-500">{user.email}</span>
                          )}
                          {!user.display_name && (
                            <span className="text-xs text-gray-500">{user.email}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span
                          className={`badge text-xs ${
                            user.is_admin
                              ? 'bg-bw-blue/20 text-bw-blue border-bw-blue/30'
                              : 'bg-gray-700/50 text-gray-400 border-gray-600/30'
                          }`}
                        >
                          {user.is_admin ? 'Admin' : 'User'}
                        </span>
                      </td>
                      <td>
                        <select
                          ref={(node) => {
                            userAgentSelectRefs.current[user.id] = node
                          }}
                          value={user.remote_agent_id || ''}
                          onChange={(e) => handleUserAgentChange(user, e.target.value)}
                          disabled={busy || noAgentsAvailable}
                          className="field min-w-[12rem] py-2 text-xs"
                        >
                          <option value="" disabled={Boolean(user.remote_agent_id)}>
                            {noAgentsAvailable ? 'No agents available' : 'Select remote agent'}
                          </option>
                          {agentOptions.map((agent) => (
                            <option key={agent.id} value={agent.id}>
                              {agent.name}
                              {agent.region ? ` - ${agent.region}` : ''}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <span
                            className={`badge text-xs ${
                              user.remote_redundancy_enabled
                                ? 'bg-emerald-400/10 text-emerald-300 border-emerald-300/30'
                                : 'bg-gray-700/50 text-gray-400 border-gray-600/30'
                            }`}
                          >
                            {user.remote_redundancy_enabled ? 'Enabled' : 'Disabled'}
                          </span>
                          <button
                            onClick={() => handleRedundancyToggle(user)}
                            disabled={busy}
                            className="btn btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            {user.remote_redundancy_enabled ? 'Disable' : 'Enable'}
                          </button>
                        </div>
                      </td>
                      <td className="text-xs text-gray-400">
                        {new Date(user.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => toggleAdmin(user)}
                            disabled={busy || (user.id === me?.user_id && user.is_admin)}
                            title={
                              user.id === me?.user_id && user.is_admin
                                ? 'Cannot remove your own admin'
                                : ''
                            }
                            className="btn btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            {user.is_admin ? 'Remove Admin' : 'Make Admin'}
                          </button>
                          <button
                            onClick={() => setResetTarget(user)}
                            disabled={busy}
                            className="btn btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            Reset Password
                          </button>
                          <button
                            onClick={() => confirmDeleteUser(user)}
                            disabled={busy || user.id === me?.user_id}
                            title={user.id === me?.user_id ? 'Cannot delete your own account' : ''}
                            className="btn btn-danger text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {confirmDialog && (
        <ConfirmDialog
          title={confirmDialog.title}
          message={confirmDialog.message}
          confirmLabel={confirmDialog.confirmLabel}
          confirmClassName={confirmDialog.confirmClassName}
          onCancel={() => setConfirmDialog(null)}
          onConfirm={confirmDialog.onConfirm}
        />
      )}

      {showCreateUser && (
        <CreateUserModal onClose={() => setShowCreateUser(false)} onSave={createUser} />
      )}

      {showCreateAgent && (
        <CreateRemoteAgentModal
          onClose={() => setShowCreateAgent(false)}
          onSave={createAgent}
        />
      )}

      {resetTarget && (
        <ResetPasswordModal
          user={resetTarget}
          onClose={() => setResetTarget(null)}
          onSave={(password) => resetPassword(resetTarget, password)}
        />
      )}

      {keyModal && (
        <ApiKeyModal
          agentName={keyModal.agentName}
          apiKey={keyModal.apiKey}
          onClose={() => setKeyModal(null)}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 bg-gray-800 border border-gray-700 text-sm text-white px-4 py-2.5 rounded-lg shadow-mat-3 z-50">
          {toast}
        </div>
      )}
    </div>
  )
}
