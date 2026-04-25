import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi } from '../hooks/useApi'
import { getAllImgs } from '../utils/images'

// ─── History detail modal ─────────────────────────────────────────────────────

function HistoryDetailModal({ record, priceCache, onClose }) {
  const { get } = useApi()
  const [detail, setDetail]     = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [imgIdx, setImgIdx]     = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const [priceData, setPriceData] = useState(null)
  const overlayRef = useRef(null)
  const cacheKey = record.auction_id

  useEffect(() => {
    if (!record.auction_id || !record.login_id) { setLoading(false); return }
    get(`/auctions/${record.auction_id}?login_id=${record.login_id}`)
      .then(async res => {
        if (res.ok) setDetail(await res.json())
        else setError('Could not load auction details.')
      })
      .catch(() => setError('Network error.'))
      .finally(() => setLoading(false))
  }, [record.auction_id, record.login_id, get])

  // Price comparison — check cache first, then fetch once detail arrives
  useEffect(() => {
    if (!cacheKey) return
    if (priceCache?.current?.[cacheKey]) { setPriceData(priceCache.current[cacheKey]); return }
    const i = detail?.item || {}
    const brand = i.brand || i.manufacturer || ''
    const model = i.modelNumber || i.model || i.sku || ''
    const title = i.title || record.title || ''
    if (!title && !brand) { setPriceData({ results: [] }); return }
    let query = brand && model ? `${brand} ${model}` : brand ? `${brand} ${title}` : title
    query = query.trim().slice(0, 200)
    setPriceData(null)
    get(`/price-compare?q=${encodeURIComponent(query)}`)
      .then(async res => {
        if (res.status === 503) { setPriceData({ error: 'no_key' }); return }
        if (!res.ok) { setPriceData({ error: 'failed' }); return }
        const data = await res.json()
        if (priceCache?.current) priceCache.current[cacheKey] = data
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
  const retail    = item.price || item.retailPrice || 0
  const bids      = detail?.computedBidHistory || detail?.bidHistory || detail?.bids || []
  const sortedBids = [...bids].sort((a, b) => (b.amount || 0) - (a.amount || 0))

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 bg-black/70 flex items-end justify-center z-50 p-0 sm:items-center sm:p-4"
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
    >
      <div role="dialog" aria-modal="true" className="card rounded-t-xl sm:rounded-xl w-full max-w-2xl max-h-[100dvh] sm:max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between p-4 sm:p-5 border-b border-gray-800 gap-3">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-white leading-snug">
              {item.title || record.title || '(Untitled)'}
            </h2>
            {(item.brand || item.manufacturer) && (
              <p className="text-xs text-gray-400 mt-0.5">
                {item.brand || item.manufacturer}
                {(item.modelNumber || item.model) ? ` · ${item.modelNumber || item.model}` : ''}
              </p>
            )}
          </div>
          <button onClick={onClose} aria-label="Close" className="btn btn-ghost shrink-0 text-lg leading-none px-2 py-1">✕</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {loading && <p className="text-gray-500 text-sm animate-pulse">Loading details…</p>}
          {error   && <p className="text-red-400 text-sm">{error}</p>}

          {/* Images */}
          {imgs.length > 0 && (
            <div>
              <div
                className="bg-gray-950 rounded-lg overflow-hidden flex items-center justify-center cursor-zoom-in h-[256px]"
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
              ['My Bid',      record.my_bid     != null ? `$${record.my_bid.toFixed(2)}`     : '—'],
              ['Final Price', record.final_price != null ? `$${record.final_price.toFixed(2)}` : '—'],
              ['Retail',      retail ? `$${retail.toFixed(2)}` : '—'],
              ['Condition',   record.condition || item.condition || '—'],
              ['Won',         record.won_at ? new Date(record.won_at).toLocaleDateString() : '—'],
              ['Bids',        sortedBids.length || '—'],
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-800 rounded p-2.5">
                <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                <p className="font-medium text-white truncate">{val}</p>
              </div>
            ))}
          </div>

          {/* Direct link */}
          {record.url && (
            <a href={record.url} target="_blank" rel="noreferrer"
              className="block text-xs text-bw-blue hover:text-bw-blue/80 underline break-all">
              {record.url}
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
          <a href={record.url} target="_blank" rel="noreferrer"
            className="btn btn-secondary w-full">
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

function exportCsv(records) {
  const headers = ['Date Won', 'Title', 'URL', 'Condition', 'Final Price', 'My Bid']
  const rows = records.map(r => [
    r.won_at ? new Date(r.won_at).toLocaleDateString() : '',
    (r.title || '').replace(/"/g, '""'),
    r.url || '',
    r.condition || '',
    r.final_price?.toFixed(2) ?? '',
    r.my_bid?.toFixed(2) ?? '',
  ].map(v => `"${v}"`).join(','))
  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'bwsniper-history.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export default function History() {
  const { get, post } = useApi()
  const [records, setRecords] = useState([])
  const [logins, setLogins] = useState([])
  const [loginId, setLoginId] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [detailRecord, setDetailRecord] = useState(null)
  const priceCache = useRef({})  // auctionId → priceData, persists across modal open/close

  useEffect(() => {
    get('/logins').then(async res => {
      if (res.ok) {
        const data = await res.json()
        setLogins(data)
        if (data.length > 0) setLoginId(data[0].id)
      }
    })
  }, [get])

  const loadHistory = useCallback(async () => {
    if (!loginId) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ login_id: loginId })
      if (search) params.set('search', search)
      const res = await get(`/history?${params}`)
      if (res.ok) setRecords(await res.json())
    } finally {
      setLoading(false)
    }
  }, [loginId, search, get])

  useEffect(() => { loadHistory() }, [loadHistory])

  async function handleRefresh() {
    if (!loginId) return
    setRefreshing(true)
    try {
      await post(`/history/refresh?login_id=${loginId}`, {})
      await loadHistory()
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-4">
      {detailRecord && (
        <HistoryDetailModal record={detailRecord} priceCache={priceCache} onClose={() => setDetailRecord(null)} />
      )}
      <div className="flex items-center gap-4 flex-wrap">
        <select
          value={loginId}
          onChange={e => setLoginId(e.target.value)}
          className="field w-auto"
        >
          {logins.map(l => (
            <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search history..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="field w-64"
        />
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn btn-primary"
        >
          {refreshing ? 'Refreshing…' : 'Refresh from BuyWander'}
        </button>
        <button
          onClick={() => exportCsv(records)}
          disabled={records.length === 0}
          className="btn btn-secondary"
        >
          Export CSV
        </button>
        <span className="text-sm text-gray-400">
          {records.length} record{records.length !== 1 ? 's' : ''}
        </span>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading history...</p>
      ) : records.length === 0 ? (
        <p className="text-gray-500">No won auctions found. Click Refresh to pull from BuyWander.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mat-table text-left">
            <thead>
              <tr>
                <th>Date Won</th>
                <th>Item</th>
                <th className="text-right">Final Price</th>
                <th className="text-right">My Bid</th>
              </tr>
            </thead>
            <tbody>
              {records.map(r => (
                <tr key={r.id}>
                  <td className="whitespace-nowrap">
                    {r.won_at ? new Date(r.won_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="max-w-md truncate">
                    <button
                      onClick={() => setDetailRecord(r)}
                      className="truncate text-left w-full hover:text-bw-blue transition-colors"
                    >
                      {r.title || r.url || '(Untitled)'}
                    </button>
                  </td>
                  <td className="text-right text-bw-green">${r.final_price?.toFixed(2)}</td>
                  <td className="text-right">${r.my_bid?.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
