import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { useApi, fmtApiError } from '../hooks/useApi'

function CreateUserModal({ onClose, onSave }) {
  const [form, setForm]   = useState({ email: '', password: '', display_name: '', is_admin: false })
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const set = (k, v) => { setForm(f => ({ ...f, [k]: v })); setError('') }

  const handleSubmit = async e => {
    e.preventDefault()
    if (form.password !== confirm) { setError('Passwords do not match'); return }
    if (form.password.length < 8)  { setError('Password must be at least 8 characters'); return }
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
            onChange={e => set('email', e.target.value)}
            className="field w-full"
            autoFocus
            required
          />
          <input
            type="text"
            placeholder="Display name (optional)"
            value={form.display_name}
            onChange={e => set('display_name', e.target.value)}
            className="field w-full"
          />
          <input
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={e => set('password', e.target.value)}
            className="field w-full"
            required
          />
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={e => { setConfirm(e.target.value); setError('') }}
            className="field w-full"
            required
          />
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={form.is_admin}
              onChange={e => set('is_admin', e.target.checked)}
              className="rounded"
            />
            Grant admin privileges
          </label>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="btn btn-primary flex-1">
              {saving ? 'Creating…' : 'Create User'}
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
  const [confirm, setConfirm]   = useState('')
  const [error, setError]       = useState('')
  const [saving, setSaving]     = useState(false)

  const handleSubmit = async e => {
    e.preventDefault()
    if (password !== confirm) { setError('Passwords do not match'); return }
    if (password.length < 8)  { setError('Password must be at least 8 characters'); return }
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
            onChange={e => { setPassword(e.target.value); setError('') }}
            className="field w-full"
            autoFocus
          />
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={e => { setConfirm(e.target.value); setError('') }}
            className="field w-full"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="btn btn-primary flex-1">
              {saving ? 'Saving…' : 'Save'}
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

export default function Admin() {
  const { user: me }          = useAuth()
  const { get, post, patch, del } = useApi()
  const [users, setUsers]           = useState([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState('')
  const [resetTarget, setResetTarget]   = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [toast, setToast]           = useState('')
  const [confirmDialog, setConfirmDialog] = useState(null) // { message, onConfirm }
  const toastTimerRef = useRef(null)

  const showToast = msg => {
    setToast(msg)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(''), 3000)
  }

  useEffect(() => () => { if (toastTimerRef.current) clearTimeout(toastTimerRef.current) }, [])

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await get('/admin/users')
      if (!res.ok) throw new Error('Failed to load users')
      setUsers(await res.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [get])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  const toggleAdmin = async (u) => {
    try {
      const res = await patch(`/admin/users/${u.id}`, { is_admin: !u.is_admin })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(fmtApiError(err, 'Update failed'))
      }
      setUsers(prev => prev.map(x => x.id === u.id ? { ...x, is_admin: !u.is_admin } : x))
      showToast(`${u.email} is ${!u.is_admin ? 'now an admin' : 'no longer an admin'}`)
    } catch (err) {
      setError(err.message)
    }
  }

  const resetPassword = async (u, newPassword) => {
    const res = await post(`/admin/users/${u.id}/reset-password`, { new_password: newPassword })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Reset failed'))
    }
    showToast(`Password reset for ${u.email}`)
  }

  const createUser = async (form) => {
    const res = await post('/admin/users', form)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(fmtApiError(err, 'Create failed'))
    }
    const newUser = await res.json()
    setUsers(prev => [...prev, newUser])
    showToast(`Created user ${newUser.email}`)
  }

  const deleteUser = (u) => {
    setConfirmDialog({
      message: `Delete ${u.email} and all their data? This cannot be undone.`,
      onConfirm: async () => {
        try {
          const res = await del(`/admin/users/${u.id}`)
          if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(fmtApiError(err, 'Delete failed'))
          }
          setUsers(prev => prev.filter(x => x.id !== u.id))
          showToast(`Deleted ${u.email}`)
        } catch (err) {
          setError(err.message)
        }
      }
    })
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">User Administration</h1>
            <p className="text-sm text-gray-400 mt-0.5">{users.length} registered user{users.length !== 1 ? 's' : ''}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowCreate(true)} className="btn btn-primary text-xs">+ Create User</button>
            <button onClick={fetchUsers} className="btn btn-secondary text-xs">Refresh</button>
          </div>
        </div>

        {error && (
          <div className="bg-bw-red/10 border border-bw-red/30 rounded-lg px-4 py-3 text-sm text-bw-red flex items-center justify-between">
            {error}
            <button onClick={() => setError('')} aria-label="Dismiss error" className="text-bw-red hover:text-bw-red/70 ml-4">✕</button>
          </div>
        )}

        <div className="card overflow-hidden p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-6 h-6 rounded-full border-2 border-bw-blue border-t-transparent animate-spin" />
            </div>
          ) : (
            <table className="mat-table w-full">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Joined</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td>
                      <div className="flex flex-col">
                        <span className="text-sm text-white font-medium">
                          {u.display_name || u.email}
                          {u.id === me?.user_id && (
                            <span className="ml-2 text-xs text-bw-blue font-normal">(you)</span>
                          )}
                        </span>
                        {u.display_name && (
                          <span className="text-xs text-gray-500">{u.email}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`badge text-xs ${u.is_admin ? 'bg-bw-blue/20 text-bw-blue border-bw-blue/30' : 'bg-gray-700/50 text-gray-400 border-gray-600/30'}`}>
                        {u.is_admin ? 'Admin' : 'User'}
                      </span>
                    </td>
                    <td className="text-xs text-gray-400">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => toggleAdmin(u)}
                          disabled={u.id === me?.user_id && u.is_admin}
                          title={u.id === me?.user_id && u.is_admin ? 'Cannot remove your own admin' : ''}
                          className="btn btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          {u.is_admin ? 'Remove Admin' : 'Make Admin'}
                        </button>
                        <button
                          onClick={() => setResetTarget(u)}
                          className="btn btn-ghost text-xs"
                        >
                          Reset Password
                        </button>
                        <button
                          onClick={() => deleteUser(u)}
                          disabled={u.id === me?.user_id}
                          title={u.id === me?.user_id ? 'Cannot delete your own account' : ''}
                          className="btn btn-danger text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {confirmDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setConfirmDialog(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            className="card w-full max-w-sm mx-4 p-6"
            onClick={e => e.stopPropagation()}
          >
            <h3 id="confirm-dialog-title" className="text-base font-semibold text-white mb-3">Confirm Action</h3>
            <p className="text-sm text-gray-300 mb-5">{confirmDialog.message}</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmDialog(null)} className="btn btn-secondary">Cancel</button>
              <button
                onClick={() => { confirmDialog.onConfirm(); setConfirmDialog(null) }}
                className="btn btn-danger"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onSave={createUser}
        />
      )}

      {resetTarget && (
        <ResetPasswordModal
          user={resetTarget}
          onClose={() => setResetTarget(null)}
          onSave={pw => resetPassword(resetTarget, pw)}
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
