/**
 * Log.jsx — Live event log page.
 *
 * On mount: fetches recent events from GET /api/events (newest first).
 * Real-time: listens for log.event WebSocket messages and prepends them.
 * Displays: timestamp, event_type badge, message, optional auction_id.
 * Filters: account selector (login_id), event type, keyword.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'

const TYPE_COLORS = {
  'snipe.won':     'bg-bw-green/20 text-bw-green border-bw-green/40',
  'snipe.lost':    'bg-bw-red/20 text-bw-red border-bw-red/40',
  'snipe.placed':  'bg-bw-blue/20 text-bw-blue border-bw-blue/40',
  'snipe.error':   'bg-bw-yellow/20 text-bw-yellow border-bw-yellow/40',
  'log.event':     'bg-gray-700/50 text-gray-300 border-gray-600',
  'auth.ok':       'bg-bw-blue/15 text-bw-blue/80 border-bw-blue/25',
  'worker.start':  'bg-bw-blue/10 text-bw-blue/60 border-bw-blue/15',
  'worker.stop':   'bg-gray-600/30 text-gray-400 border-gray-600',
}

function typeBadgeClass(type) {
  return TYPE_COLORS[type] || 'bg-gray-700/50 text-gray-400 border-gray-600'
}

function formatTs(isoString) {
  if (!isoString) return '—'
  try {
    const d = new Date(isoString)
    return d.toLocaleString(undefined, {
      month:  'short',
      day:    'numeric',
      hour:   '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return isoString
  }
}

export default function Log() {
  const { get } = useApi()

  const [logins, setLogins]       = useState([])
  const [loginId, setLoginId]     = useState('')   // '' = all accounts
  const [events, setEvents]       = useState([])
  const [loading, setLoading]     = useState(true)
  const [keyword, setKeyword]     = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [paused, setPaused]       = useState(false)
  const pausedRef = useRef(false)

  // keep pausedRef in sync so the WS callback can read it without stale closure
  useEffect(() => { pausedRef.current = paused }, [paused])

  // ── Load logins ───────────────────────────────────────────────────────────
  useEffect(() => {
    get('/logins').then(async res => {
      if (!res.ok) return
      setLogins(await res.json())
    })
  }, [get])

  // ── Fetch historical events ───────────────────────────────────────────────
  const fetchHistory = useCallback(async () => {
    setLoading(true)
    try {
      const qs = loginId ? `?login_id=${loginId}&limit=500` : '?limit=500'
      const res = await get(`/events${qs}`)
      if (res.ok) {
        setEvents(await res.json())
      }
    } finally {
      setLoading(false)
    }
  }, [loginId, get])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  // ── WebSocket: prepend live events ────────────────────────────────────────
  const handleWsMessage = useCallback((data) => {
    if (pausedRef.current) return

    // Accept both log.event and direct snipe status events
    const evType = data.type || data.event_type
    if (!evType) return

    const newEv = {
      id:         `live-${Date.now()}-${Math.random()}`,
      login_id:   data.login_id   || null,
      event_type: evType,
      message:    data.message    || data.msg || JSON.stringify(data),
      auction_id: data.auction_id || null,
      timestamp:  data.timestamp  || new Date().toISOString(),
      live:       true,
    }
    setEvents(prev => [newEv, ...prev].slice(0, 2000)) // cap at 2000 rows
  }, [])

  useWebSocket(handleWsMessage)

  // ── Derived: filtered view ────────────────────────────────────────────────
  const visible = events.filter(ev => {
    if (loginId && ev.login_id && ev.login_id !== loginId) return false
    if (typeFilter && ev.event_type !== typeFilter) return false
    if (keyword) {
      const kw = keyword.toLowerCase()
      const msg = (ev.message || '').toLowerCase()
      const aid = (ev.auction_id || '').toLowerCase()
      if (!msg.includes(kw) && !aid.includes(kw)) return false
    }
    return true
  })

  // Collect unique event types for the type filter dropdown
  const eventTypes = [...new Set(events.map(e => e.event_type).filter(Boolean))].sort()

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-[calc(100vh-52px)]">

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-gray-800 bg-gray-950">
        <h1 className="text-sm font-semibold text-white mr-1">Event Log</h1>

        {/* Account filter */}
        <select
          value={loginId}
          onChange={e => setLoginId(e.target.value)}
          className="field w-auto"
        >
          <option value="">All accounts</option>
          {logins.map(l => (
            <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>
          ))}
        </select>

        {/* Type filter */}
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="field w-auto"
        >
          <option value="">All types</option>
          {eventTypes.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        {/* Keyword search */}
        <input
          type="text"
          placeholder="Filter by message or auction ID…"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          className="field flex-1 min-w-[180px]"
        />

        {/* Pause live updates */}
        <button
          onClick={() => setPaused(p => !p)}
          className={`btn text-xs ${
            paused
              ? 'bg-bw-yellow/20 text-bw-yellow border border-bw-yellow/40 hover:bg-bw-yellow/30'
              : 'btn-ghost'
          }`}
        >
          {paused ? '▶ Resume' : '⏸ Pause'}
        </button>

        {/* Refresh history */}
        <button
          onClick={fetchHistory}
          disabled={loading}
          className="btn btn-ghost text-xs"
        >
          ↺ Refresh
        </button>

        <span className="text-xs text-gray-600 ml-auto">
          {visible.length} event{visible.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* ── Event list ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto font-mono text-xs">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <p className="text-gray-400 text-sm font-sans">Loading events…</p>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex items-center justify-center h-40">
            <p className="text-gray-500 text-sm font-sans">No events found.</p>
          </div>
        ) : (
          <table className="w-full border-collapse">
            <thead className="sticky top-0 bg-gray-900 z-10">
              <tr className="text-left text-gray-500 text-xs uppercase tracking-wide">
                <th className="px-4 py-2 font-medium w-36">Time</th>
                <th className="px-4 py-2 font-medium w-36">Type</th>
                <th className="px-4 py-2 font-medium">Message</th>
                <th className="px-4 py-2 font-medium w-36">Auction</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((ev, idx) => (
                <tr
                  key={ev.id || idx}
                  className={`border-t border-gray-800/50 transition-colors hover:bg-gray-800/40 ${
                    ev.live ? 'animate-pulse-once' : ''
                  }`}
                >
                  {/* Timestamp */}
                  <td className="px-4 py-1.5 text-gray-500 whitespace-nowrap">
                    {formatTs(ev.timestamp)}
                  </td>

                  {/* Type badge */}
                  <td className="px-4 py-1.5">
                    <span className={`badge text-xs whitespace-nowrap ${typeBadgeClass(ev.event_type)}`}>
                      {ev.event_type || '?'}
                    </span>
                  </td>

                  {/* Message */}
                  <td className="px-4 py-1.5 text-gray-300 max-w-0">
                    <span className="block truncate" title={ev.message}>{ev.message || '—'}</span>
                  </td>

                  {/* Auction ID */}
                  <td className="px-4 py-1.5 text-gray-500 whitespace-nowrap">
                    {ev.auction_id ? (
                      <span className="truncate block max-w-[130px]" title={ev.auction_id}>
                        {ev.auction_id.slice(0, 12)}…
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
