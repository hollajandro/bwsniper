import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../context/AuthContext'
import { getAllImgs } from '../utils/images'

// ─── Constants ───────────────────────────────────────────────────────────────

const STATUS_COLORS = {
  Loading:  'bg-gray-700/50 text-gray-400 border border-gray-600/50',
  Watching: 'bg-bw-blue/20 text-bw-blue border border-bw-blue/30',
  Sniped:   'bg-bw-yellow/20 text-bw-yellow border border-bw-yellow/30',
  Won:      'bg-bw-green/20 text-bw-green border border-bw-green/30',
  Lost:     'bg-bw-red/20 text-bw-red border border-bw-red/30',
  Ended:    'bg-gray-700/50 text-gray-400 border border-gray-600/50',
  Error:    'bg-bw-red/20 text-bw-red border border-bw-red/30',
}

const TERMINAL = new Set(['Won', 'Lost', 'Ended', 'Error', 'Deleted'])

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtSecs(s) {
  if (s === null || s === undefined) return '—'
  s = Math.max(0, Math.floor(s))
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  if (s >= 60)   return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${s}s`
}

// ─── Auction detail modal (from snipe click) ─────────────────────────────────

function snipeNeedsAttention(snipe) {
  return !TERMINAL.has(snipe.status)
    && !snipe.bid_placed
    && !snipe.is_me
    && snipe.current_bid > snipe.bid_amount
}

function SnipeDetailModal({ snipe, priceCache, onClose }) {
  const { get } = useApi()
  const [detail, setDetail]     = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [imgIdx, setImgIdx]     = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const [priceData, setPriceData] = useState(null)
  const overlayRef = useRef(null)
  const cacheKey = snipe.auction_uuid || snipe.id

  // Evict oldest half of the price cache when it exceeds 500 entries to prevent
  // unbounded memory growth from repeated modal opens across different auctions.
  const MAX_PRICE_CACHE = 500
  function _setCache(key, data) {
    if (priceCache?.current[key] !== undefined) return  // already cached
    const cache = priceCache?.current || {}
    if (Object.keys(cache).length >= MAX_PRICE_CACHE) {
      const keys = Object.keys(cache)
      for (let i = 0; i < Math.floor(keys.length / 2); i++) delete priceCache.current[keys[i]]
    }
    if (priceCache?.current) priceCache.current[key] = data
  }

  useEffect(() => {
    if (!snipe.auction_uuid || !snipe.login_id) { setLoading(false); return }
    get(`/auctions/${snipe.auction_uuid}?login_id=${snipe.login_id}`)
      .then(async res => {
        if (res.ok) setDetail(await res.json())
        else setError('Failed to load auction details.')
      })
      .catch(() => setError('Network error.'))
      .finally(() => setLoading(false))
  }, [snipe.auction_uuid, snipe.login_id, get])

  // Price comparison — check cache first, then fetch once detail arrives
  useEffect(() => {
    if (!cacheKey) return
    if (priceCache?.current?.[cacheKey]) { setPriceData(priceCache.current[cacheKey]); return }
    const i = detail?.item || {}
    const brand = i.brand || i.manufacturer || ''
    const model = i.modelNumber || i.model || i.sku || ''
    const title = i.title || snipe.title || ''
    if (!title && !brand) { setPriceData({ results: [] }); return }
    let query = brand && model ? `${brand} ${model}` : brand ? `${brand} ${title}` : title
    query = query.trim().slice(0, 200)
    setPriceData(null)
    get(`/price-compare?q=${encodeURIComponent(query)}`)
      .then(async res => {
        if (res.status === 503) { setPriceData({ error: 'no_key' }); return }
        if (!res.ok) { setPriceData({ error: 'failed' }); return }
        const data = await res.json()
        _setCache(cacheKey, data)
        setPriceData(data)
      })
      .catch(() => setPriceData({ error: 'failed' }))
  }, [cacheKey, detail, get, priceCache])

  useEffect(() => {
    const handler = e => {
      if (e.key === 'Escape') { if (lightbox) setLightbox(false); else onClose() }
      if (lightbox) {
        const imgs = getAllImgs(detail?.item || {})
        if (e.key === 'ArrowLeft')  setImgIdx(i => (i - 1 + imgs.length) % imgs.length)
        if (e.key === 'ArrowRight') setImgIdx(i => (i + 1) % imgs.length)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, lightbox, detail])

  const item      = detail?.item || {}
  const imgs      = getAllImgs(item)
  const wb        = detail?.winningBid || {}
  const retail    = item.price || item.retailPrice || 0
  const bids      = detail?.computedBidHistory || detail?.bidHistory || detail?.bids || []
  const sortedBids = [...bids].sort((a, b) => (b.amount || 0) - (a.amount || 0))
  const url       = snipe.url || (snipe.auction_uuid ? `https://www.buywander.com/auction/${snipe.auction_uuid}` : '')

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 bg-black/70 flex items-end justify-center z-50 p-0 sm:items-center sm:p-4"
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="detail-modal-title" className="bg-gray-900 border border-gray-700 rounded-t-xl sm:rounded-xl w-full max-w-2xl max-h-[100dvh] sm:max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between p-4 sm:p-5 border-b border-gray-800 gap-3">
          <div className="flex-1 min-w-0">
            <h2 id="detail-modal-title" className="text-base font-semibold text-white leading-snug">
              {item.title || snipe.title || '(Untitled)'}
            </h2>
            {(item.brand || item.manufacturer) && (
              <p className="text-xs text-gray-400 mt-0.5">
                {item.brand || item.manufacturer}
                {(item.modelNumber || item.model) ? ` · ${item.modelNumber || item.model}` : ''}
              </p>
            )}
          </div>
          <button onClick={onClose} aria-label="Close" className="text-gray-500 hover:text-white shrink-0 text-lg leading-none">✕</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {loading && <p className="text-gray-500 text-sm animate-pulse">Loading details…</p>}
          {error   && <p className="text-red-400 text-sm">{error}</p>}

          {/* Images */}
          {imgs.length > 0 && (
            <div>
              <div
                className="bg-gray-950 rounded-lg overflow-hidden flex items-center justify-center cursor-zoom-in h-[280px]"
                onClick={() => setLightbox(true)}
                title="Click to enlarge"
              >
                <img src={imgs[imgIdx]} alt={item.title || ''} className="max-w-full max-h-full object-contain"
                  onError={e => { e.currentTarget.style.opacity = '0.2' }} />
              </div>
              {imgs.length > 1 && (
                <div className="flex gap-1.5 mt-2 overflow-x-auto pb-1">
                  {imgs.map((u, i) => (
                    <button key={i} onClick={() => setImgIdx(i)}
                      className={`shrink-0 w-14 h-14 rounded overflow-hidden border-2 transition-colors bg-gray-800 ${i === imgIdx ? 'border-bw-blue' : 'border-transparent hover:border-gray-600'}`}>
                      <img src={u} alt="" className="w-full h-full object-contain"
                        onError={e => { e.currentTarget.parentElement.style.display = 'none' }} />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 text-sm">
            {[
              ['My Bid',      snipe.bid_amount != null ? `$${snipe.bid_amount.toFixed(2)}` : '—'],
              ['Current Bid', wb.amount ? `$${wb.amount.toFixed(2)}` : '—'],
              ['Retail',      retail ? `$${retail.toFixed(2)}` : '—'],
              ['Status',      snipe.status || '—'],
              ['Condition',   item.condition || '—'],
              ['Bids',        bids.length || snipe.bid_count || '—'],
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-800 rounded p-2.5">
                <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                <p className="font-medium text-white truncate">{val}</p>
              </div>
            ))}
          </div>

          {/* Direct link */}
          {url && (
            <a href={url} target="_blank" rel="noreferrer"
              className="block text-xs text-bw-blue hover:text-bw-blue/80 underline break-all">
              {url}
            </a>
          )}

          {/* Description */}
          {(item.description || item.longDescription) && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Description</h3>
              <p className="text-sm text-gray-300 whitespace-pre-line leading-relaxed">
                {item.description || item.longDescription}
              </p>
            </div>
          )}

          {/* Seller notes */}
          {(item.notes || item.sellerNotes) && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Seller Notes</h3>
              <p className="text-sm text-gray-300 whitespace-pre-line leading-relaxed">
                {item.notes || item.sellerNotes}
              </p>
            </div>
          )}

          {/* Price comparison */}
          <div>
            <div className="flex items-baseline gap-2 mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Price Comparison</h3>
              {priceData?.query && <span className="text-xs text-gray-600 truncate">"{priceData.query}"</span>}
            </div>
            {priceData === null ? (
              <p className="text-gray-500 text-sm animate-pulse">Searching Google Shopping…</p>
            ) : priceData.error === 'no_key' ? (
              <p className="text-xs text-gray-500">Add a <a href="https://serper.dev" target="_blank" rel="noreferrer" className="text-bw-blue hover:underline">serper.dev</a> API key in Settings to enable price comparison.</p>
            ) : priceData.error ? (
              <p className="text-gray-500 text-sm">Price comparison unavailable.</p>
            ) : priceData.results?.length === 0 ? (
              <p className="text-gray-500 text-sm">No listings found for this item.</p>
            ) : (
              <div className="space-y-1">
                {priceData.results.map((r, i) => (
                  <a key={i} href={r.link} target="_blank" rel="noreferrer"
                    className="flex items-center gap-3 px-3 py-2 rounded bg-gray-800/60 hover:bg-gray-800 transition-colors group">
                    <span className="text-xs text-gray-600 w-4 shrink-0 text-right">{i + 1}</span>
                    <span className="font-mono font-semibold text-bw-green text-sm shrink-0 w-16 text-right">{r.price_str}</span>
                    <span className="text-xs text-gray-300 truncate flex-1">{r.source}</span>
                    <span className="text-xs text-gray-500 group-hover:text-bw-blue transition-colors shrink-0 truncate max-w-[40%] hidden sm:block">{r.title}</span>
                    <span className="text-gray-600 group-hover:text-bw-blue transition-colors shrink-0 text-xs">↗</span>
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Bid history */}
          {sortedBids.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Bid History ({sortedBids.length})</h3>
              <div className="rounded border border-gray-800 overflow-hidden">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="text-gray-500 border-b border-gray-800 bg-gray-800/50">
                      <th className="px-3 py-1.5 text-right">Amount</th>
                      <th className="px-3 py-1.5 text-left">Bidder</th>
                      <th className="px-3 py-1.5 text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedBids.slice(0, 10).map((b, i) => (
                      <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                        <td className="px-3 py-1.5 text-right font-semibold text-white">${(b.amount || 0).toFixed(2)}</td>
                        <td className="px-3 py-1.5 text-gray-300">@{b.handle || b.bidderHandle || '—'}</td>
                        <td className="px-3 py-1.5 text-right text-gray-500">
                          {(b.placedAt || b.createdAt) ? new Date(b.placedAt || b.createdAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800">
          <a href={url} target="_blank" rel="noreferrer"
            className="block w-full text-center py-2 rounded bg-gray-700 hover:bg-gray-600 text-sm transition-colors">
            Open in Browser ↗
          </a>
        </div>
      </div>

      {/* Lightbox */}
      {lightbox && imgs.length > 0 && (
        <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-[70]"
          onClick={() => setLightbox(false)}>
          {imgs.length > 1 && (
            <button aria-label="Previous image" className="absolute left-4 top-1/2 -translate-y-1/2 text-white text-3xl bg-black/40 hover:bg-black/70 rounded-full w-12 h-12 flex items-center justify-center"
              onClick={e => { e.stopPropagation(); setImgIdx(i => (i - 1 + imgs.length) % imgs.length) }}>‹</button>
          )}
          <img src={imgs[imgIdx]} alt={item.title || ''} className="max-w-[90vw] max-h-[90vh] object-contain select-none"
            onClick={e => e.stopPropagation()} onError={e => { e.currentTarget.style.opacity = '0.2' }} />
          {imgs.length > 1 && (
            <button aria-label="Next image" className="absolute right-4 top-1/2 -translate-y-1/2 text-white text-3xl bg-black/40 hover:bg-black/70 rounded-full w-12 h-12 flex items-center justify-center"
              onClick={e => { e.stopPropagation(); setImgIdx(i => (i + 1) % imgs.length) }}>›</button>
          )}
          <div className="absolute top-4 right-4 flex items-center gap-3">
            {imgs.length > 1 && <span className="text-white/60 text-sm">{imgIdx + 1} / {imgs.length}</span>}
            <button aria-label="Close image viewer" className="text-white/60 hover:text-white text-xl" onClick={() => setLightbox(false)}>✕</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Edit modal ──────────────────────────────────────────────────────────────

function EditModal({ snipe, onSave, onClose }) {
  const { put } = useApi()
  const [bid, setBid]     = useState(String(snipe.bid_amount))
  const [secs, setSecs]   = useState(String(snipe.snipe_seconds))
  const [saving, setSaving] = useState(false)
  const [err, setErr]     = useState('')

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      const body = {}
      const bidVal  = parseFloat(bid)
      const secsVal = parseInt(secs)
      if (!isNaN(bidVal)  && bidVal  > 0) body.bid_amount    = bidVal
      if (!isNaN(secsVal) && secsVal > 0) body.snipe_seconds = secsVal
      const res = await put(`/snipes/${snipe.id}`, body)
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        setErr(d.detail || 'Save failed')
      } else {
        onSave(await res.json())
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-modal-title"
        className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-80 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <h3 id="edit-modal-title" className="font-semibold">Edit Snipe</h3>
        <p className="text-xs text-gray-400 truncate">{snipe.title || snipe.url}</p>
        {err && <p className="text-xs text-red-400">{err}</p>}
        <form onSubmit={handleSave} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Bid amount ($)</label>
            <input type="number" step="0.01" min="0.01" required
              value={bid} onChange={e => setBid(e.target.value)}
              className="field" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Snipe seconds (1–120)</label>
            <input type="number" min="1" max="120" required
              value={secs} onChange={e => setSecs(e.target.value)}
              className="field" />
          </div>
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

// ─── Snipe row ───────────────────────────────────────────────────────────────

function SnipeRow({ snipe, onDelete, onEdit, onItemClick }) {
  const [secsLeft, setSecsLeft] = useState(null)

  useEffect(() => {
    if (!snipe.end_time) { setSecsLeft(null); return }
    const update = () => {
      const s = (new Date(snipe.end_time) - Date.now()) / 1000
      setSecsLeft(s)
    }
    update()
    const t = setInterval(update, 1000)
    return () => clearInterval(t)
  }, [snipe.end_time])

  const isTerminal = TERMINAL.has(snipe.status)
  const needsAttention = snipeNeedsAttention(snipe)

  return (
    <tr className={`border-b border-gray-800 hover:bg-gray-800/50 ${needsAttention ? 'bg-bw-red/5' : ''}`}>
      <td className="px-3 py-2">
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[snipe.status] || 'bg-gray-700/50 text-gray-400 border border-gray-600/50'}`}>
          {snipe.status}
        </span>
      </td>
      <td className="px-3 py-2 text-sm max-w-xs">
        <button
          onClick={() => onItemClick(snipe)}
          className="truncate block hover:text-bw-blue transition-colors text-left w-full"
        >
          {snipe.title || snipe.url}
        </button>
        {needsAttention && (
          <p className="mt-1 text-xs text-bw-red font-medium">Above max bid - update needed</p>
        )}
      </td>
      <td className="px-3 py-2 text-sm text-right font-mono">
        ${snipe.bid_amount?.toFixed(2)}
      </td>
      <td className={`px-3 py-2 text-sm text-right font-mono ${needsAttention ? 'text-bw-red' : snipe.is_me ? 'text-bw-green' : ''}`}>
        {snipe.current_bid > 0 ? `$${snipe.current_bid.toFixed(2)}` : '—'}
        {snipe.is_me && <span className="ml-1 text-xs text-bw-green">★</span>}
      </td>
      <td className="px-3 py-2 text-xs text-gray-400">
        {snipe.winner_handle ? `@${snipe.winner_handle}` : '—'}
      </td>
      <td className={`px-3 py-2 text-sm text-right font-mono ${secsLeft !== null && secsLeft < 60 ? 'text-bw-yellow' : ''}`}>
        {fmtSecs(secsLeft)}
      </td>
      <td className="px-3 py-2 text-sm text-center text-gray-400">{snipe.snipe_seconds}s</td>
      <td className="px-3 py-2 text-right">
        <div className="flex gap-2 justify-end">
          {!isTerminal && (
            <button onClick={() => onEdit(snipe)}
              className="text-xs text-bw-blue hover:text-bw-blue/80 transition-colors">
              Edit
            </button>
          )}
          {!isTerminal && (
            <button onClick={() => onDelete(snipe.id)}
              className="text-xs text-bw-red hover:text-bw-red/80 transition-colors">
              Remove
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

// ─── Add-snipe form ──────────────────────────────────────────────────────────

function AddSnipeForm({ logins, defaultSnipeSecs, onAdded }) {
  const { post } = useApi()
  const [url, setUrl]         = useState('')
  const [bid, setBid]         = useState('')
  const [secs, setSecs]       = useState(String(defaultSnipeSecs || 5))
  const [loginId, setLoginId] = useState(logins[0]?.id || '')
  const [adding, setAdding]   = useState(false)
  const [err, setErr]         = useState('')

  // Keep loginId in sync when logins load
  useEffect(() => {
    if (!loginId && logins.length > 0) setLoginId(logins[0].id)
  }, [logins, loginId])

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    setAdding(true)
    try {
      const res = await post('/snipes', {
        login_id:      loginId,
        url:           url.trim(),
        bid_amount:    parseFloat(bid),
        snipe_seconds: parseInt(secs),
      })
      const data = await res.json()
      if (!res.ok) { setErr(data.detail || 'Failed to add snipe'); return }
      onAdded(data)
      setUrl('')
      setBid('')
    } catch (ex) {
      setErr(ex.message || 'Network error')
    } finally {
      setAdding(false)
    }
  }

  if (logins.length === 0) return null

  return (
    <form onSubmit={handleSubmit} className="bg-gray-800/60 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3 text-gray-300">Add New Snipe</h3>
      {err && <p className="text-xs text-bw-red mb-2">{err}</p>}
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex-1 min-w-48">
          <label className="block text-xs text-gray-400 mb-1">BuyWander auction URL</label>
          <input type="url" required placeholder="https://www.buywander.com/auctions/..."
            value={url} onChange={e => setUrl(e.target.value)}
            className="field" />
        </div>
        <div className="w-28">
          <label className="block text-xs text-gray-400 mb-1">Max bid ($)</label>
          <input type="number" step="0.01" min="0.01" required
            value={bid} onChange={e => setBid(e.target.value)}
            className="field" />
        </div>
        <div className="w-24">
          <label className="block text-xs text-gray-400 mb-1">Snipe at (s)</label>
          <input type="number" min="1" max="120" required
            value={secs} onChange={e => setSecs(e.target.value)}
            className="field" />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Account</label>
          <select value={loginId} onChange={e => setLoginId(e.target.value)}
            className="field w-auto">
            {logins.map(l => (
              <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>
            ))}
          </select>
        </div>
        <button type="submit" disabled={adding} className="btn btn-primary whitespace-nowrap self-end">
          {adding ? 'Adding…' : '+ Snipe'}
        </button>
      </div>
    </form>
  )
}

// ─── Win toast ───────────────────────────────────────────────────────────────

function WinToast({ title, price, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 8000)
    return () => clearTimeout(t)
  }, [onClose])

  return (
    <div className="fixed top-4 right-4 z-50 bg-gray-900 border border-bw-green/50 rounded-lg px-5 py-4 shadow-2xl max-w-xs animate-bounce-once">
      <p className="font-bold text-lg text-bw-green">🎉 You Won!</p>
      <p className="text-sm mt-1 truncate text-gray-200">{title}</p>
      {price != null && <p className="text-sm font-mono mt-0.5 text-white">Final: ${Number(price).toFixed(2)}</p>}
      <button onClick={onClose} aria-label="Dismiss" className="absolute top-2 right-3 text-gray-400 hover:text-white text-sm">✕</button>
    </div>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const { get, del } = useApi()
  const { user } = useAuth()
  const [snipes, setSnipes]     = useState([])
  const [logins, setLogins]     = useState([])
  const [settings, setSettings] = useState(null)
  const [loading, setLoading]   = useState(true)
  const [editSnipe, setEditSnipe] = useState(null)
  const [detailSnipe, setDetailSnipe] = useState(null)
  const priceCache = useRef({})  // auctionId → priceData, persists across modal open/close
  const [winToast, setWinToast]   = useState(null)

  const loadData = useCallback(async () => {
    try {
      const [snipeRes, loginRes, settRes] = await Promise.all([
        get('/snipes'),
        get('/logins'),
        get('/settings'),
      ])
      if (snipeRes.ok) setSnipes(await snipeRes.json())
      if (loginRes.ok) setLogins(await loginRes.json())
      if (settRes.ok)  setSettings(await settRes.json())
    } finally {
      setLoading(false)
    }
  }, [get])

  useEffect(() => { loadData() }, [loadData])

  // Real-time WebSocket updates
  const handleWS = useCallback((msg) => {
    if (msg.type === 'snipe.status_changed') {
      setSnipes(prev => {
        const found = prev.some(s => s.id === msg.data.snipe_id)
        if (found) return prev.map(s => s.id === msg.data.snipe_id ? { ...s, ...msg.data } : s)
        return prev // new snipes arrive via add form; ignore unknown IDs here
      })
    }
    if (msg.type === 'snipe.won') {
      setWinToast({ title: msg.data.title, price: msg.data.final_price })
    }
  }, [])
  useWebSocket(handleWS)

  async function handleDelete(snipeId) {
    await del(`/snipes/${snipeId}`)
    setSnipes(prev => prev.filter(s => s.id !== snipeId))
  }

  function handleEditSave(updated) {
    setSnipes(prev => prev.map(s => s.id === updated.id ? updated : s))
    setEditSnipe(null)
  }

  function handleSnipeAdded(snipe) {
    setSnipes(prev => [snipe, ...prev])
  }

  function handleItemClick(snipe) {
    if (snipe.auction_uuid) setDetailSnipe(snipe)
    else window.open(snipe.url, '_blank', 'noreferrer')
  }

  const active = useMemo(() => snipes.filter(s => !TERMINAL.has(s.status)), [snipes])
  const past = useMemo(() => snipes.filter(s => TERMINAL.has(s.status) && s.status !== 'Deleted'), [snipes])
  const attentionSnipes = useMemo(() => active.filter(snipeNeedsAttention), [active])

  const stats = useMemo(() => {
    const acc = snipes.reduce((a, s) => {
      if (s.status === 'Deleted') return a
      a.total++
      if (s.status === 'Won') {
        a.won++
        if (s.final_price != null) {
          a.saved  += s.bid_amount - s.final_price
          a.discountSum += (s.bid_amount - s.final_price) / s.bid_amount * 100
          a.discountN++
        }
      } else if (s.status === 'Lost') {
        a.lost++
      }
      return a
    }, { total: 0, won: 0, lost: 0, saved: 0, discountSum: 0, discountN: 0 })

    const outcomes = acc.won + acc.lost
    return {
      totalSnipes:  acc.total,
      wonCount:     acc.won,
      lostCount:    acc.lost,
      winRate:      outcomes > 0 ? Math.round((acc.won / outcomes) * 100) : null,
      totalSaved:   acc.saved,
      avgDiscount:  acc.discountN > 0
        ? Math.round(acc.discountSum / acc.discountN * 10) / 10
        : null,
    }
  }, [snipes])

  if (loading) return <div className="p-8 text-gray-400">Loading…</div>

  const headerCls = 'text-xs text-gray-400 uppercase border-b border-gray-700'
  const thCls     = 'px-3 py-2'

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {winToast && (
        <WinToast title={winToast.title} price={winToast.price}
          onClose={() => setWinToast(null)} />
      )}
      {editSnipe && (
        <EditModal snipe={editSnipe}
          onSave={handleEditSave}
          onClose={() => setEditSnipe(null)} />
      )}
      {detailSnipe && (
        <SnipeDetailModal snipe={detailSnipe} priceCache={priceCache}
          onClose={() => setDetailSnipe(null)} />
      )}

      {/* Add snipe */}
      <AddSnipeForm
        logins={logins}
        defaultSnipeSecs={settings?.defaults?.snipe_seconds}
        onAdded={handleSnipeAdded}
      />

      {/* Statistics */}
      {stats.totalSnipes > 0 && (
        <section className="flex flex-wrap gap-3 items-stretch">
          {/* Win Rate — primary stat */}
          <div className="bg-gray-800/60 border border-gray-800 rounded-lg px-5 py-4 flex items-center gap-5 flex-1 min-w-[220px]">
            <div>
              <div className="text-3xl font-bold text-white tabular-nums leading-none">
                {stats.winRate === null ? '—' : `${stats.winRate}%`}
              </div>
              <div className="text-xs text-gray-400 mt-1.5 uppercase tracking-wide">Win Rate</div>
            </div>
            <div className="w-px h-10 bg-gray-700 shrink-0" />
            <div className="flex gap-5">
              <div>
                <div className="text-lg font-semibold text-bw-green tabular-nums">{stats.wonCount}</div>
                <div className="text-xs text-gray-500 mt-0.5">Won</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-bw-red tabular-nums">{stats.lostCount}</div>
                <div className="text-xs text-gray-500 mt-0.5">Lost</div>
              </div>
            </div>
          </div>

          {/* Savings */}
          {(stats.totalSaved > 0 || stats.avgDiscount !== null) && (
            <div className="bg-gray-800/60 border border-gray-800 rounded-lg px-5 py-4 flex items-center gap-5">
              {stats.totalSaved > 0 && (
                <div>
                  <div className="text-2xl font-bold text-white tabular-nums leading-none">
                    ${stats.totalSaved.toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-400 mt-1.5 uppercase tracking-wide">Saved</div>
                </div>
              )}
              {stats.totalSaved > 0 && stats.avgDiscount !== null && (
                <div className="w-px h-10 bg-gray-700 shrink-0" />
              )}
              {stats.avgDiscount !== null && (
                <div>
                  <div className="text-2xl font-bold text-white tabular-nums leading-none">
                    {stats.avgDiscount}%
                  </div>
                  <div className="text-xs text-gray-400 mt-1.5 uppercase tracking-wide">Avg Off</div>
                </div>
              )}
            </div>
          )}

          {/* Total — small chip */}
          <div className="bg-gray-800/60 border border-gray-800 rounded-lg px-4 py-3 flex items-center gap-2 self-center">
            <span className="text-sm font-semibold text-gray-300 tabular-nums">{stats.totalSnipes}</span>
            <span className="text-xs text-gray-500">tracked</span>
          </div>
        </section>
      )}

      {/* Active snipes */}
      <section>
        <h2 className="text-base font-semibold mb-3 text-gray-100">
          Active Snipes
          {active.length > 0
            ? <span className="ml-2 inline-flex items-center justify-center w-5 h-5 rounded-full bg-bw-blue text-white text-xs font-bold">{active.length}</span>
            : <span className="ml-2 text-gray-500 font-normal text-sm">(0)</span>
          }
        </h2>
        {attentionSnipes.length > 0 && (
          <div className="mb-3 rounded-lg border border-bw-red/30 bg-bw-red/10 px-4 py-3">
            <p className="text-sm font-medium text-bw-red">
              {attentionSnipes.length === 1
                ? '1 active snipe is above your max bid'
                : `${attentionSnipes.length} active snipes are above your max bids`}
            </p>
            <p className="mt-1 text-xs text-bw-red/80">
              Review those snipes and raise the max bid if you still want them to fire.
            </p>
          </div>
        )}
        {active.length === 0 ? (
          <p className="text-gray-500 text-sm">No active snipes. Add one above or use the Browse page.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-left">
              <thead>
                <tr className={headerCls}>
                  <th className={thCls}>Status</th>
                  <th className={thCls}>Item</th>
                  <th className={`${thCls} text-right`}>My Bid</th>
                  <th className={`${thCls} text-right`}>Current</th>
                  <th className={thCls}>Leader</th>
                  <th className={`${thCls} text-right`}>Time Left</th>
                  <th className={`${thCls} text-center`}>Snipe At</th>
                  <th className={thCls}></th>
                </tr>
              </thead>
              <tbody>
                {active.map(s => (
                  <SnipeRow key={s.id} snipe={s}
                    onDelete={handleDelete} onEdit={setEditSnipe} onItemClick={handleItemClick} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Past snipes */}
      {past.length > 0 && (
        <section>
          <h2 className="text-base font-semibold mb-3 text-gray-100">
            Past Snipes
            <span className="ml-2 text-gray-500 font-normal text-sm">({past.length})</span>
          </h2>
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-left">
              <thead>
                <tr className={headerCls}>
                  <th className={thCls}>Status</th>
                  <th className={thCls}>Item</th>
                  <th className={`${thCls} text-right`}>My Bid</th>
                  <th className={`${thCls} text-right`}>Final</th>
                  <th className={thCls}>Leader</th>
                  <th className={`${thCls} text-right`}>Ended</th>
                  <th className={`${thCls} text-center`}>Snipe At</th>
                  <th className={thCls}></th>
                </tr>
              </thead>
              <tbody>
                {past.map(s => (
                  <SnipeRow key={s.id} snipe={s}
                    onDelete={handleDelete} onEdit={setEditSnipe} onItemClick={handleItemClick} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* BW logins — compact status row */}
      <div className="flex items-center gap-3 flex-wrap pt-1 border-t border-gray-800/60">
        <span className="text-xs text-gray-600 uppercase tracking-wide shrink-0">Accounts</span>
        {logins.map(l => (
          <span key={l.id} className="inline-flex items-center gap-1.5 text-xs text-gray-400">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${l.is_active ? 'bg-bw-green' : 'bg-gray-600'}`} />
            {l.display_name || l.bw_email}
          </span>
        ))}
        {logins.length === 0 && (
          <Link to="/settings" className="text-xs text-bw-blue hover:underline">
            Add a BuyWander account →
          </Link>
        )}
      </div>
    </div>
  )
}
