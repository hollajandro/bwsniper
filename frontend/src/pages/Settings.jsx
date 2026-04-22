import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi, fmtApiError } from '../hooks/useApi'

// Fields hidden from the generic key→input renderer (handled explicitly)
const NOTIF_META_KEYS = new Set(['enabled'])

function ApiKeyInput({ value, onChange }) {
  const [show, setShow] = useState(false)
  return (
    <div className="flex gap-2">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder="sk-…"
        className="field flex-1 font-mono"
      />
      <button type="button" onClick={() => setShow(s => !s)}
        className="btn btn-secondary text-xs">
        {show ? 'Hide' : 'Show'}
      </button>
    </div>
  )
}
// SMTP fields hidden when use_tls is false
const SMTP_AUTH_KEYS = new Set(['username', 'password'])

export default function Settings() {
  const { get, post, put, del } = useApi()
  const [settings, setSettings]   = useState(null)
  const [logins, setLogins]       = useState([])
  const [locations, setLocations] = useState([])
  const [saveStatus, setSaveStatus] = useState('') // '' | 'saving' | 'saved' | 'error'
  const [msg, setMsg]             = useState('')
  const [testingChannel, setTestingChannel] = useState(null)
  const [testResults, setTestResults]       = useState({})
  const [newKeyword, setNewKeyword] = useState('')

  const [bwEmail, setBwEmail] = useState('')
  const [bwPass, setBwPass]   = useState('')
  const [addingLogin, setAddingLogin] = useState(false)

  const skipSaveRef = useRef(true) // skip auto-save on initial load
  const putRef = useRef(put)
  useEffect(() => { putRef.current = put }, [put])

  // ── Load ────────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    skipSaveRef.current = true
    const [sRes, lRes] = await Promise.all([get('/settings'), get('/logins')])
    if (sRes.ok) setSettings(await sRes.json())
    if (lRes.ok) {
      const loginsData = await lRes.json()
      setLogins(loginsData)
      if (loginsData.length > 0) {
        const locRes = await get(`/auctions/locations/list?login_id=${loginsData[0].id}`)
        if (locRes.ok) setLocations(await locRes.json())
      }
    }
  }, [get])

  useEffect(() => { load() }, [load])

  // ── Auto-save (debounced 800 ms) ────────────────────────────────────────────
  useEffect(() => {
    if (!settings) return
    if (skipSaveRef.current) {
      skipSaveRef.current = false
      return
    }
    setSaveStatus('saving')
    const timer = setTimeout(async () => {
      try {
        const res = await putRef.current('/settings', {
          defaults: settings.defaults,
          notifications: settings.notifications,
          serper_api_key: settings.serper_api_key,
          version: settings.updated_at,
        })
        if (!res.ok) {
          setSaveStatus('error')
          return
        }
        const updated = await res.json()
        skipSaveRef.current = true
        setSettings(updated)
        setSaveStatus('saved')
      } catch {
        setSaveStatus('error')
      }
    }, 800)
    return () => clearTimeout(timer)
  }, [settings])

  // Clear "saved" badge after 2 s
  useEffect(() => {
    if (saveStatus !== 'saved') return
    const t = setTimeout(() => setSaveStatus(''), 2000)
    return () => clearTimeout(t)
  }, [saveStatus])

  // ── BW login helpers ────────────────────────────────────────────────────────
  async function addBwLogin(e) {
    e.preventDefault()
    setAddingLogin(true)
    setMsg('')
    try {
      const res = await post('/logins', { bw_email: bwEmail, bw_password: bwPass })
      if (res.ok) {
        setBwEmail(''); setBwPass('')
        setMsg('BuyWander account added!')
        await load()
      } else {
        const err = await res.json().catch(() => ({}))
        setMsg(fmtApiError(err, 'Failed to add login.'))
      }
    } finally {
      setAddingLogin(false)
    }
  }

  async function removeBwLogin(id) {
    await del(`/logins/${id}`)
    setLogins(prev => prev.filter(l => l.id !== id))
    setMsg('Login removed.')
  }

  // ── Settings mutators ────────────────────────────────────────────────────────
  function updateSetting(section, key, value) {
    setSettings(prev => ({ ...prev, [section]: { ...prev[section], [key]: value } }))
  }

  function updateNotif(key, value) {
    setSettings(prev => ({ ...prev, notifications: { ...prev.notifications, [key]: value } }))
  }

  function updateNotifChannel(channel, key, value) {
    setSettings(prev => ({
      ...prev,
      notifications: {
        ...prev.notifications,
        [channel]: { ...prev.notifications[channel], [key]: value },
      },
    }))
  }

  function addKeyword() {
    const kw = newKeyword.trim()
    if (!kw) return
    const current = settings.notifications?.keyword_watches || []
    if (current.includes(kw)) return
    updateNotif('keyword_watches', [...current, kw])
    setNewKeyword('')
  }

  function removeKeyword(kw) {
    const current = settings.notifications?.keyword_watches || []
    const locs = { ...(settings.notifications?.keyword_watch_locations || {}) }
    delete locs[kw]
    updateNotif('keyword_watches', current.filter(k => k !== kw))
    updateNotif('keyword_watch_locations', locs)
  }

  // ── Channel test ─────────────────────────────────────────────────────────────
  async function testChannel(channel) {
    setTestingChannel(channel)
    setTestResults(prev => ({ ...prev, [channel]: null }))
    try {
      const res = await post(`/settings/test-notification/${channel}`, {})
      if (res.ok) {
        setTestResults(prev => ({ ...prev, [channel]: { ok: true, msg: 'Sent!' } }))
      } else {
        const err = await res.json().catch(() => ({}))
        setTestResults(prev => ({ ...prev, [channel]: { ok: false, msg: fmtApiError(err, 'Failed') } }))
      }
    } catch {
      setTestResults(prev => ({ ...prev, [channel]: { ok: false, msg: 'Network error' } }))
    } finally {
      setTestingChannel(null)
    }
  }

  if (!settings) return <div className="p-8 text-gray-400">Loading…</div>

  const notif = settings.notifications || {}

  return (
    <div className="h-full overflow-y-auto">
    <div className="p-6 max-w-3xl space-y-8">

      {/* Status bar */}
      <div className="flex items-center gap-3 min-h-[24px]">
        {msg && <span className="text-sm text-gray-300">{msg}</span>}
        <span className="ml-auto text-xs">
          {saveStatus === 'saving' && <span className="text-gray-400">Saving…</span>}
          {saveStatus === 'saved'  && <span className="text-bw-green">Saved</span>}
          {saveStatus === 'error'  && <span className="text-bw-red">Save failed</span>}
        </span>
      </div>

      {/* BuyWander accounts */}
      <section>
        <h2 className="text-lg font-semibold mb-3">BuyWander Accounts</h2>
        <div className="space-y-2 mb-4">
          {logins.map(l => (
            <div key={l.id} className="flex items-center justify-between bg-gray-800 rounded px-4 py-2">
              <div className="text-sm">
                <span className={l.is_active ? 'text-bw-green' : 'text-gray-500'}>●</span>
                {' '}{l.display_name || l.bw_email}
                <span className="text-gray-500 ml-2">({l.bw_email})</span>
              </div>
              <button onClick={() => removeBwLogin(l.id)} className="btn btn-danger text-xs">Remove</button>
            </div>
          ))}
        </div>
        <form onSubmit={addBwLogin} className="flex gap-2 items-end">
          <input type="email" placeholder="BuyWander email" value={bwEmail} onChange={e => setBwEmail(e.target.value)} required
            disabled={addingLogin} className="field flex-1" />
          <input type="password" placeholder="BuyWander password" value={bwPass} onChange={e => setBwPass(e.target.value)} required
            disabled={addingLogin} className="field flex-1" />
          <button type="submit" disabled={addingLogin}
            className="btn btn-primary whitespace-nowrap">
            {addingLogin ? 'Adding…' : 'Add Account'}
          </button>
        </form>
      </section>

      {/* Defaults */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Defaults</h2>
        <div className="space-y-3">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Default snipe seconds</label>
            <input type="number" min={1} max={120}
              value={settings.defaults?.snipe_seconds || 5}
              onChange={e => updateSetting('defaults', 'snipe_seconds', parseInt(e.target.value) || 5)}
              className="field w-32" />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Default browse location</label>
            <select
              value={settings.defaults?.default_location_id || ''}
              onChange={e => updateSetting('defaults', 'default_location_id', e.target.value || null)}
              className="field w-auto"
            >
              <option value="">— None —</option>
              {locations.map(loc => (
                <option key={loc.id} value={loc.id}>{loc.name}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Integrations */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Integrations</h2>
        <div className="bg-gray-800 rounded p-4">
          <div className="flex items-start justify-between mb-1">
            <label className="text-sm font-medium">Serper.dev API Key</label>
            <a href="https://serper.dev" target="_blank" rel="noreferrer"
              className="text-xs text-bw-blue hover:underline">
              Get free key ↗
            </a>
          </div>
          <p className="text-xs text-gray-500 mb-2">
            Powers the Google Shopping price comparison shown in auction details. Free tier includes 2,500 searches/month.
          </p>
          <ApiKeyInput
            value={settings.serper_api_key ?? ''}
            onChange={v => setSettings(prev => ({ ...prev, serper_api_key: v }))}
          />
        </div>
      </section>

      {/* Notifications */}
      <section>
        <h2 className="text-lg font-semibold mb-4">Notifications</h2>

        {/* Remind before */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-1">Remind before auction end (seconds)</label>
          <input type="number" min={0}
            value={notif.remind_before_seconds ?? 300}
            onChange={e => updateNotif('remind_before_seconds', parseInt(e.target.value) || 0)}
            className="field w-32" />
        </div>

        {/* Notify on */}
        <div className="bg-gray-800 rounded p-4 mb-3">
          <p className="text-sm font-medium mb-3">Notify me when</p>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={notif.notify_on_won ?? true}
                onChange={e => updateNotif('notify_on_won', e.target.checked)} />
              I win a bid
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={notif.notify_on_lost ?? true}
                onChange={e => updateNotif('notify_on_lost', e.target.checked)} />
              I lose a bid
            </label>
          </div>
        </div>

        {/* Keyword watches */}
        <div className="bg-gray-800 rounded p-4 mb-3">
          <p className="text-sm font-medium mb-1">Keyword watches</p>
          <p className="text-xs text-gray-500 mb-3">
            Get notified when a new auction is listed that matches any of these keywords (checked every 5 min).
          </p>
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              placeholder="e.g. Milwaukee, iPhone 15…"
              value={newKeyword}
              onChange={e => setNewKeyword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addKeyword())}
              className="field flex-1"
            />
            <button onClick={addKeyword}
              className="btn btn-primary whitespace-nowrap">
              Add
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {(notif.keyword_watches || []).map(kw => {
              const kwLocs = notif.keyword_watch_locations?.[kw] || []
              return (
                <span key={kw} className="flex items-center gap-1 bg-gray-700 rounded-full px-3 py-0.5 text-xs">
                  {kw}
                  {kwLocs.length > 0 && (
                    <span title={`Restricted to ${kwLocs.length} location(s)`}>📍</span>
                  )}
                  {locations.length > 0 && (
                    <select
                      multiple
                      value={kwLocs}
                      onChange={e => {
                        const selected = Array.from(e.target.selectedOptions).map(o => o.value)
                        const locs = { ...(notif.keyword_watch_locations || {}), [kw]: selected }
                        if (selected.length === 0) delete locs[kw]
                        updateNotif('keyword_watch_locations', locs)
                      }}
                      title="Restrict to specific locations (Ctrl/Cmd+click to multi-select; deselect all for any location)"
                      className="ml-1 bg-gray-600 border border-gray-500 rounded text-xs max-h-20 max-w-[120px]"
                      style={{ minWidth: '80px' }}
                    >
                      {locations.map(loc => (
                        <option key={loc.id} value={loc.id}>{loc.name}</option>
                      ))}
                    </select>
                  )}
                  <button onClick={() => removeKeyword(kw)} aria-label={`Remove keyword ${kw}`} className="text-gray-400 hover:text-bw-red ml-1">✕</button>
                </span>
              )
            })}
            {(notif.keyword_watches || []).length === 0 &&
              <span className="text-xs text-gray-500">No keywords yet</span>}
          </div>
        </div>

        {/* Per-channel config */}
        {['telegram', 'smtp', 'pushover', 'gotify'].map(ch => {
          const cfg = notif[ch] || {}
          const isSmtp = ch === 'smtp'
          const useTls = cfg.use_tls !== false

          return (
            <div key={ch} className="bg-gray-800 rounded p-4 mb-3">
              <div className="flex items-center gap-2 mb-2">
                <input type="checkbox" checked={cfg.enabled || false}
                  onChange={e => updateNotifChannel(ch, 'enabled', e.target.checked)} />
                <span className="font-medium text-sm capitalize">{ch === 'smtp' ? 'SMTP Email' : ch}</span>
                {cfg.enabled && (
                  <>
                    <button
                      onClick={() => testChannel(ch)}
                      disabled={testingChannel === ch}
                      className="btn btn-ghost text-xs ml-auto"
                    >
                      {testingChannel === ch ? 'Sending…' : 'Test'}
                    </button>
                    {testResults[ch] && (
                      <span className={`text-xs ${testResults[ch].ok ? 'text-bw-green' : 'text-bw-red'}`}>
                        {testResults[ch].msg}
                      </span>
                    )}
                  </>
                )}
              </div>
              {cfg.enabled && (
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {Object.entries(cfg)
                    .filter(([k]) => {
                      if (NOTIF_META_KEYS.has(k)) return false
                      if (isSmtp && SMTP_AUTH_KEYS.has(k) && !useTls) return false
                      return true
                    })
                    .map(([k, v]) => (
                      <div key={k}>
                        <label className="text-xs text-gray-400 capitalize">{k.replace(/_/g, ' ')}</label>
                        {typeof v === 'boolean' ? (
                          <div className="flex items-center gap-2 mt-1">
                            <input type="checkbox" checked={v}
                              onChange={e => updateNotifChannel(ch, k, e.target.checked)} />
                            <span className="text-xs text-gray-400">Yes</span>
                          </div>
                        ) : (
                          <input
                            type={k.includes('password') || k.includes('token') || k.includes('key') ? 'password' : 'text'}
                            value={v ?? ''}
                            onChange={e => updateNotifChannel(ch, k, e.target.value)}
                            className="field w-full" />
                        )}
                      </div>
                    ))}
                </div>
              )}
            </div>
          )
        })}
      </section>
    </div>
    </div>
  )
}
