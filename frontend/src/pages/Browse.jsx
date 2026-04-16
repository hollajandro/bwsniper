/**
 * Browse.jsx — Browse live BuyWander auctions with filters and inline sniping.
 *
 * Features:
 *   - Location dropdown (fetched from /auctions/locations/list)
 *   - Condition multi-select checkboxes
 *   - Price range (min/max retail)
 *   - Quick-filter buttons (No Reserve, Ending Today)
 *   - Sort + keyword search
 *   - Auction detail modal: description, seller notes, bid history
 *   - "Snipe This" modal: login selector, bid amount, snipe_seconds → POST /snipes
 *   - Pagination
 */
import { useState, useEffect, useLayoutEffect, useCallback, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../context/AuthContext'
import { getAllImgs } from '../utils/images'

const SORTS = [
  { value: 'EndingSoonest',       label: 'Ending Soonest' },
  { value: 'EndingLatest',        label: 'Ending Latest' },
  { value: 'NewArrivals',         label: 'New Arrivals' },
  { value: 'CurrentPriceLowest',  label: 'Price ↑' },
  { value: 'CurrentPriceHighest', label: 'Price ↓' },
  { value: 'RetailPriceLowest',   label: 'Retail ↑' },
  { value: 'RetailPriceHighest',  label: 'Retail ↓' },
  { value: 'BidsLowest',          label: 'Bids ↑' },
  { value: 'BidsHighest',         label: 'Bids ↓' },
]

const CONDITIONS = [
  { value: 'New',            label: 'New' },
  { value: 'AppearsNew',     label: 'Appears New' },
  { value: 'GentlyUsed',     label: 'Gently Used' },
  { value: 'UsedGood',       label: 'Good' },
  { value: 'Used',           label: 'Used' },
  { value: 'UsedFair',       label: 'Fair' },
  { value: 'Damaged',        label: 'Damaged' },
  { value: 'EasyFix',        label: 'Easy Fix' },
  { value: 'HeavyUse',       label: 'Heavy Use' },
  { value: 'MajorFix',       label: 'Major Fix' },
  { value: 'MixedCondition', label: 'Mixed' },
]

const ENDED_TTL = 7 * 24 * 3600 * 1000  // 7 days in ms

// ─── Grid layout size configs ─────────────────────────────────────────────────
// 'small'  → thumbnail grid (more columns, smaller images)
// 'medium' → default (current behaviour)
// 'large'  → showcase grid (fewer columns, ~3× taller images)
const GRID_COLS = {
  small:  'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3',
  medium: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4',
  large:  'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5',
}
// Container height / img max-height per size (medium = current h-28 / 112 px; large ≈ 3×)
const IMG_H    = { small: 'h-20',      medium: 'h-28',     large: 'h-[21rem]' }
const IMG_MAXH = { small: 'max-h-20',  medium: 'max-h-28', large: 'max-h-[21rem]' }

// Tab identifiers — single source of truth to avoid stringly-typed comparisons
const TABS = /** @type {const} */ ({ LIVE: 'live', ENDED: 'ended', RECENT: 'recent' })

// ─── Condition color map (Feature 11) ────────────────────────────────────────
const CONDITION_COLORS = {
  New:            'bg-green-700 text-green-100',
  AppearsNew:     'bg-green-800 text-green-200',
  GentlyUsed:     'bg-blue-800 text-blue-200',
  UsedGood:       'bg-blue-900 text-blue-300',
  Used:           'bg-gray-700 text-gray-300',
  UsedFair:       'bg-yellow-800 text-yellow-200',
  Damaged:        'bg-red-900 text-red-300',
  EasyFix:        'bg-orange-900 text-orange-300',
  HeavyUse:       'bg-red-800 text-red-300',
  MajorFix:       'bg-red-700 text-red-200',
  MixedCondition: 'bg-purple-900 text-purple-300',
}

function ConditionBadge({ condition }) {
  if (!condition) return <span className="text-gray-500">—</span>
  const color = CONDITION_COLORS[condition] || 'bg-gray-700 text-gray-300'
  const cond = CONDITIONS.find(c => c.value === condition)
  const label = cond ? cond.label : condition
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${color}`}>{label}</span>
  )
}

// ─── Bid count badge (Feature 16) ────────────────────────────────────────────
function BidCountBadge({ count }) {
  if (!count || count === 0) return null
  if (count >= 5) return <span className="text-xs px-1.5 py-0.5 rounded bg-red-900/70 text-red-300 font-medium">🔥 Hot</span>
  return <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900/70 text-yellow-300 font-medium">↑ Active</span>
}

// Quick filters are applied client-side (BW API ignores auctionFilters).
// 'Sniped' is also client-side — shows only items you have a snipe for.
const QUICK_FILTERS = [
  { value: 'Sniped',             label: 'Sniped' },
  { value: 'Watched',            label: 'Watched' },
  { value: 'NoBidsYet',          label: 'No Bids Yet' },
  { value: 'ThreeDollarsOrLess', label: '$3 or Less' },
  { value: 'EndsToday',          label: 'Ends Today' },
  { value: 'EndsTomorrow',       label: 'Ends Tomorrow' },
  { value: 'Over90PercentOff',   label: '90%+ Off' },
]

// Predicate per quick-filter value. Receives (auction, snipesMap, watchlist).
const QUICK_FILTER_FNS = {
  Sniped:             (a, sm)     => sm.has(a.id) || sm.has(a.handle),
  Watched:            (a, sm, wl) => wl.has(a.handle) || wl.has(a.id),
  NoBidsYet:          (a)         => !(a.winningBid?.amount > 0),
  ThreeDollarsOrLess: (a)         => (a.winningBid?.amount ?? 0) <= 3,
  EndsToday:          (a)         => { const s = (new Date(a.endDate).getTime() - Date.now()) / 1000; return s >= 0 && s < 86400 },
  EndsTomorrow:       (a)         => { const s = (new Date(a.endDate).getTime() - Date.now()) / 1000; return s >= 86400 && s < 172800 },
  Over90PercentOff:   (a)         => { const r = a.item?.price ?? 0; const b = a.winningBid?.amount ?? 0; return r > 0 && (r - b) / r >= 0.9 },
}

function getItemImage(item) {
  if (!item) return null
  return item.imageUrl
    || item.thumbnailUrl
    || item.thumbnail
    || (Array.isArray(item.images) && item.images.length && (item.images[0]?.url || item.images[0]))
    || (Array.isArray(item.photos) && item.photos.length && (item.photos[0]?.url || item.photos[0]))
    || null
}

function fmtSecs(s) {
  if (s === null || s === undefined || s < 0) return 'Ended'
  s = Math.floor(s)
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  if (s >= 60)   return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${s}s`
}

function auctionUrl(auction) {
  return auction.url
    || (auction.id ? `https://www.buywander.com/auction/${auction.id}` : '')
}

/**
 * Parse quoted phrases from a search string.
 * e.g. '"apple watch" series 3' →
 *   { apiQuery: 'apple watch series 3', exactPhrases: ['apple watch'] }
 * Unquoted terms are sent to the API as-is for broad matching;
 * exactPhrases are then applied client-side to enforce exact phrase order.
 */
function parseSearchPhrases(raw) {
  const exactPhrases = []
  const apiQuery = raw
    .replace(/"([^"]+)"/g, (_, phrase) => {
      exactPhrases.push(phrase.trim().toLowerCase())
      return phrase  // keep words in query so API still has them
    })
    .trim()
  return { apiQuery, exactPhrases }
}

// ─── Auction Detail Modal ─────────────────────────────────────────────────────

function AuctionDetailModal({ auction, loginId, logins, defaultSnipeSec, priceCache, onClose, onSnipe, snipe, onSnipeCancel, onSnipeUpdate, watchlist, onWatchToggle }) {
  const { get } = useApi()
  const [detail, setDetail]     = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(true)
  const [detailError, setDetailError]     = useState('')
  const [showSnipe, setShowSnipe] = useState(false)
  const [snipeSuccess, setSnipeSuccess] = useState('')
  const [selectedImg, setSelectedImg] = useState(0)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const overlayRef = useRef(null)

  // Snipe editing state (if a snipe exists for this auction)
  const [editingSnipe, setEditingSnipe] = useState(false)
  const [editBid, setEditBid]           = useState(snipe?.bid_amount?.toFixed(2) ?? '')
  const [editSec, setEditSec]           = useState(String(snipe?.snipe_seconds ?? ''))
  const [snipeOpBusy, setSnipeOpBusy]   = useState(false)
  const [snipeOpError, setSnipeOpError] = useState('')

  // Price comparison state: null=loading, object with results or error
  const [priceData, setPriceData] = useState(null)

  useEffect(() => {
    const id = auction.id
    if (!id) { setLoadingDetail(false); return }
    get(`/auctions/${id}?login_id=${loginId}`)
      .then(async res => {
        if (res.ok) { setDetail(await res.json()); setSelectedImg(0) }
        else setDetailError('Failed to load auction details.')
      })
      .catch(() => setDetailError('Network error loading details.'))
      .finally(() => setLoadingDetail(false))
  }, [auction.id, loginId, get])

  // Fetch price comparison, using cache if available
  useEffect(() => {
    const cached = priceCache?.current?.[auction.id]
    if (cached) { setPriceData(cached); return }

    const i = auction.item || {}
    const brand = i.brand || i.manufacturer || ''
    const model = i.modelNumber || i.model || i.sku || ''
    const title = i.title || ''
    if (!title && !brand) { setPriceData({ results: [] }); return }

    // Build query: brand+model is most specific; fall back to brand+title, then title alone
    let query
    if (brand && model) {
      query = `${brand} ${model}`
    } else if (brand) {
      query = `${brand} ${title}`
    } else {
      query = title
    }
    query = query.trim().slice(0, 200)

    setPriceData(null)
    get(`/price-compare?q=${encodeURIComponent(query)}`)
      .then(async res => {
        if (res.status === 503) { setPriceData({ error: 'no_key' }); return }
        if (!res.ok) { setPriceData({ error: 'failed' }); return }
        const data = await res.json()
        if (priceCache?.current) priceCache.current[auction.id] = data
        setPriceData(data)
      })
      .catch(() => setPriceData({ error: 'failed' }))
  }, [auction.id, get, priceCache])

  const item     = (detail?.item) || auction.item || {}

  useEffect(() => {
    const handler = e => {
      if (e.key === 'Escape') {
        if (lightboxOpen) setLightboxOpen(false)
        else onClose()
      }
      if (lightboxOpen) {
        const imgs = getAllImgs(item)
        if (e.key === 'ArrowLeft') setSelectedImg(i => (i - 1 + imgs.length) % imgs.length)
        if (e.key === 'ArrowRight') setSelectedImg(i => (i + 1) % imgs.length)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, lightboxOpen, item])
  const wb       = detail?.winningBid || auction.winningBid || {}
  const bidAmt   = wb.amount || 0
  const retail   = item.price || 0
  const offPct   = retail && bidAmt ? Math.round(100 * (1 - bidAmt / retail)) : null
  const loc      = (detail || auction).storeLocation || {}
  const locStr   = [loc.city, loc.state].filter(Boolean).join(', ') || loc.name || '—'
  const endDate  = (detail || auction).endDate
  const secsLeft = endDate ? (new Date(endDate) - Date.now()) / 1000 : null
  const url      = auctionUrl(detail || auction)

  const description = item.description || item.longDescription || item.details || ''
  const notes = item.notes || item.sellerNotes || item.itemNotes || item.note || item.sellerNote
    || (detail?.notes) || (detail?.sellerNotes) || (detail?.auctionNotes)
    || (detail?.note) || (detail?.sellerNote) || (detail?.auctionNote)
    || (auction.notes) || (auction.sellerNotes) || (auction.auctionNotes) || ''

  const bids = detail?.computedBidHistory || detail?.bidHistory || detail?.bids || []
  const sortedBids = [...bids].sort((a, b) => (b.amount || 0) - (a.amount || 0))

  async function handleSnipeSubmit(payload) {
    const res = await onSnipe(payload)
    if (res) throw res
    setSnipeSuccess(`Snipe added!`)
    setTimeout(() => setSnipeSuccess(''), 4000)
    setShowSnipe(false)
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
    >
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-800 gap-3">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-white leading-snug">
              {item.title || auction.item?.title || '(Untitled)'}
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
        <div className="flex-1 overflow-y-auto p-5 space-y-5">

          {/* Photo gallery */}
          {(() => {
            const imgs = getAllImgs(item)
            if (imgs.length === 0) return null
            const src = imgs[selectedImg] ?? imgs[0]
            return (
              <div>
                <div
                  className="bg-gray-950 rounded-lg overflow-hidden flex items-center justify-center cursor-zoom-in h-[280px]"
                  onClick={() => setLightboxOpen(true)}
                  title="Click to enlarge"
                >
                  <img
                    key={src}
                    src={src}
                    alt={item.title || ''}
                    className="max-w-full max-h-full object-contain"
                    onError={e => { e.currentTarget.style.opacity = '0.2' }}
                  />
                </div>
                {imgs.length > 1 && (
                  <div className="flex gap-1.5 mt-2 overflow-x-auto pb-1">
                    {imgs.map((url, idx) => (
                      <button
                        key={idx}
                        onClick={() => setSelectedImg(idx)}
                        className={`shrink-0 w-14 h-14 rounded overflow-hidden border-2 transition-colors bg-gray-800 ${
                          selectedImg === idx ? 'border-bw-blue' : 'border-transparent hover:border-gray-600'
                        }`}
                      >
                        <img
                          src={url} alt=""
                          className="w-full h-full object-contain"
                          onError={e => { e.currentTarget.parentElement.style.display = 'none' }}
                        />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })()}

          {/* Key stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
            <div className="bg-gray-800 rounded p-3">
              <div className="text-xs text-gray-400 mb-0.5">Current Bid</div>
              <div className="font-mono font-semibold text-white">
                {bidAmt ? `$${bidAmt.toFixed(2)}` : '—'}
              </div>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="text-xs text-gray-400 mb-0.5">Retail</div>
              <div className="font-mono text-gray-300">
                {retail ? `$${retail.toFixed(2)}` : '—'}
                {offPct != null && (
                  <span className="text-bw-green ml-1 text-xs">({offPct}% off)</span>
                )}
              </div>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="text-xs text-gray-400 mb-0.5">Condition</div>
              <div className="text-gray-300"><ConditionBadge condition={item.condition} /></div>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="text-xs text-gray-400 mb-0.5">Time Left</div>
              <div className={`font-mono ${secsLeft != null && secsLeft < 300 ? 'text-bw-yellow' : 'text-gray-300'}`}>
                {secsLeft != null ? fmtSecs(secsLeft) : '—'}
              </div>
            </div>
            {endDate && (
              <div className="bg-gray-800 rounded p-3">
                <div className="text-xs text-gray-400 mb-0.5">Ends</div>
                <div className="text-gray-300 text-xs">
                  {new Date(endDate).toLocaleString(undefined, {
                    month: 'short', day: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}
                </div>
              </div>
            )}
            <div className="bg-gray-800 rounded p-3">
              <div className="text-xs text-gray-400 mb-0.5">Location</div>
              <div className="text-gray-300 text-xs">{locStr}</div>
            </div>
          </div>

          {/* URL */}
          {url && (
            <a href={url} target="_blank" rel="noreferrer"
              className="block text-xs text-bw-blue hover:text-bw-blue/80 underline break-all">
              {url}
            </a>
          )}

          {/* Loading / error state */}
          {loadingDetail && (
            <p className="text-gray-400 text-sm">Loading details…</p>
          )}
          {detailError && (
            <p className="text-bw-red text-sm">{detailError}</p>
          )}

          {/* Description */}
          {description && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                Description
              </h3>
              <p className="text-sm text-gray-300 whitespace-pre-line leading-relaxed">
                {description}
              </p>
            </div>
          )}

          {/* Seller notes */}
          {!loadingDetail && notes && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                Seller Notes
              </h3>
              <p className="text-sm text-gray-300 whitespace-pre-line leading-relaxed">
                {notes}
              </p>
            </div>
          )}

          {/* Your Snipe panel */}
          {snipe && (
            <div className="bg-bw-blue/10 border border-bw-blue/30 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-bw-blue uppercase tracking-wide">⚡ Your Snipe</h3>
                {!editingSnipe && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setEditingSnipe(true); setEditBid(snipe.bid_amount.toFixed(2)); setEditSec(String(snipe.snipe_seconds)) }}
                      className="text-xs text-gray-400 hover:text-white transition-colors"
                    >Edit</button>
                    <button
                      onClick={async () => {
                        if (!window.confirm('Cancel this snipe?')) return
                        setSnipeOpBusy(true); setSnipeOpError('')
                        try { await onSnipeCancel(snipe.id) }
                        catch (e) { setSnipeOpError(e.message || 'Failed') }
                        finally { setSnipeOpBusy(false) }
                      }}
                      disabled={snipeOpBusy}
                      className="text-xs text-bw-red hover:text-bw-red/70 transition-colors disabled:opacity-50"
                    >Cancel Snipe</button>
                  </div>
                )}
              </div>
              {!editingSnipe ? (
                <div className="flex gap-4 text-sm">
                  <div><span className="text-xs text-gray-400">Bid</span> <span className="font-semibold text-white">${snipe.bid_amount.toFixed(2)}</span></div>
                  <div><span className="text-xs text-gray-400">Timing</span> <span className="text-gray-300">{snipe.snipe_seconds}s before end</span></div>
                  <div><span className="text-xs text-gray-400">Status</span> <span className="text-gray-300 capitalize">{snipe.status}</span></div>
                </div>
              ) : (
                <form onSubmit={async e => {
                  e.preventDefault()
                  setSnipeOpBusy(true); setSnipeOpError('')
                  try {
                    await onSnipeUpdate(snipe.id, {
                      bid_amount: parseFloat(editBid),
                      snipe_seconds: parseInt(editSec, 10),
                    })
                    setEditingSnipe(false)
                  } catch (err) {
                    setSnipeOpError(err.message || 'Failed to update')
                  } finally { setSnipeOpBusy(false) }
                }} className="space-y-2">
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <label className="block text-xs text-gray-400 mb-1">Max Bid ($)</label>
                      <input type="number" min="0.01" step="0.01" value={editBid} onChange={e => setEditBid(e.target.value)} required
                        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-bw-blue" />
                    </div>
                    <div className="w-24">
                      <label className="block text-xs text-gray-400 mb-1">Seconds</label>
                      <input type="number" min="1" max="120" value={editSec} onChange={e => setEditSec(e.target.value)} required
                        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-bw-blue" />
                    </div>
                  </div>
                  {snipeOpError && <p className="text-bw-red text-xs">{snipeOpError}</p>}
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setEditingSnipe(false)} className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-xs transition-colors">Cancel</button>
                    <button type="submit" disabled={snipeOpBusy} className="px-3 py-1 rounded bg-bw-blue hover:bg-bw-blue/80 text-xs font-medium transition-colors disabled:opacity-50">
                      {snipeOpBusy ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                </form>
              )}
              {snipeOpError && !editingSnipe && <p className="text-bw-red text-xs mt-1">{snipeOpError}</p>}
            </div>
          )}

          {/* Price comparison */}
          <div>
            <div className="flex items-baseline gap-2 mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                Price Comparison
              </h3>
              {priceData?.query && (
                <span className="text-xs text-gray-600 truncate">"{priceData.query}"</span>
              )}
            </div>
            {priceData === null ? (
              <p className="text-gray-500 text-sm animate-pulse">Searching Google Shopping…</p>
            ) : priceData.error === 'no_key' ? (
              <p className="text-xs text-gray-500 leading-relaxed">
                Add a free{' '}
                <a href="https://serper.dev" target="_blank" rel="noreferrer"
                  className="text-bw-blue hover:underline">serper.dev</a>{' '}
                API key via the{' '}
                <code className="bg-gray-800 px-1 rounded text-gray-300">SERPER_API_KEY</code>{' '}
                environment variable to enable live price comparison.
              </p>
            ) : priceData.error ? (
              <p className="text-gray-500 text-sm">Price comparison unavailable.</p>
            ) : priceData.results?.length === 0 ? (
              <p className="text-gray-500 text-sm">No listings found for this item.</p>
            ) : (
              <div className="space-y-1">
                {priceData.results.map((r, i) => (
                  <a
                    key={i}
                    href={r.link}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-3 px-3 py-2 rounded bg-gray-800/60 hover:bg-gray-800 transition-colors group"
                  >
                    <span className="text-xs text-gray-600 w-4 shrink-0 text-right">{i + 1}</span>
                    <span className="font-mono font-semibold text-bw-green text-sm shrink-0 w-16 text-right">
                      {r.price_str}
                    </span>
                    <span className="text-xs text-gray-300 truncate flex-1">{r.source}</span>
                    <span className="text-xs text-gray-500 group-hover:text-bw-blue transition-colors shrink-0 truncate max-w-[40%] hidden sm:block">
                      {r.title}
                    </span>
                    <span className="text-gray-600 group-hover:text-bw-blue transition-colors shrink-0 text-xs">↗</span>
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Bid history */}
          {!loadingDetail && detail && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                Bid History {sortedBids.length > 0 && `(${sortedBids.length})`}
              </h3>
              {sortedBids.length === 0 ? (
                <p className="text-sm text-gray-500">No bids yet.</p>
              ) : (
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
                      {sortedBids.map((bid, idx) => {
                        const ts = bid.placedAt || bid.createdAt
                        return (
                          <tr key={idx} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                            <td className="px-3 py-1.5 text-right font-semibold text-white">
                              ${(bid.amount || 0).toFixed(2)}
                            </td>
                            <td className="px-3 py-1.5 text-gray-300">
                              @{bid.handle || '?'}
                            </td>
                            <td className="px-3 py-1.5 text-right text-gray-500">
                              {ts ? new Date(ts).toLocaleString(undefined, {
                                month: 'short', day: 'numeric',
                                hour: '2-digit', minute: '2-digit',
                              }) : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800 flex items-center gap-3">
          {snipeSuccess && (
            <span className="text-bw-green text-xs font-medium flex-1">{snipeSuccess}</span>
          )}
          {!snipeSuccess && url && (
            <a href={url} target="_blank" rel="noreferrer"
              className="px-4 py-2 bg-gray-700 rounded text-sm hover:bg-gray-600 transition-colors whitespace-nowrap">
              Open in Browser
            </a>
          )}
          {url && watchlist && onWatchToggle && (() => {
            const handle = (detail || auction).handle || ''
            const isWatched = watchlist.has(handle)
            return (
              <button
                onClick={() => {
                  if (!isWatched) {
                    onWatchToggle(handle, url, item.title || '')
                  }
                }}
                className={`px-4 py-2 rounded text-sm transition-colors ${isWatched ? 'bg-gray-700 text-bw-yellow' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
              >
                {isWatched ? '★ Watching' : '☆ Watch'}
              </button>
            )
          })()}
          {(() => {
            const sl = endDate ? (new Date(endDate) - Date.now()) / 1000 : null
            const isEnded = sl !== null && sl <= 0
            if (snipe) return null  // snipe panel in body handles this
            return (
              <button
                onClick={() => !isEnded && setShowSnipe(true)}
                disabled={isEnded}
                className={`flex-1 py-2 rounded text-sm font-medium transition-colors ${
                  isEnded ? 'bg-gray-700 text-gray-500 cursor-not-allowed' : 'bg-bw-blue hover:bg-bw-blue/85'
                }`}
              >
                {isEnded ? 'Auction Ended' : 'Snipe This'}
              </button>
            )
          })()}
        </div>
      </div>

      {showSnipe && (
        <SnipeModal
          auction={detail || auction}
          logins={logins}
          defaultSnipeSec={defaultSnipeSec}
          onClose={() => setShowSnipe(false)}
          onSubmit={handleSnipeSubmit}
        />
      )}

      {lightboxOpen && (() => {
        const imgs = getAllImgs(item)
        if (!imgs.length) return null
        const go = delta => setSelectedImg(i => (i + delta + imgs.length) % imgs.length)
        return (
          <div
            className="fixed inset-0 bg-black/90 flex items-center justify-center z-[70]"
            onClick={() => setLightboxOpen(false)}
          >
            {/* Prev */}
            {imgs.length > 1 && (
              <button
                aria-label="Previous image"
                className="absolute left-4 top-1/2 -translate-y-1/2 text-white text-3xl bg-black/40 hover:bg-black/70 rounded-full w-12 h-12 flex items-center justify-center transition-colors"
                onClick={e => { e.stopPropagation(); go(-1) }}
              >‹</button>
            )}

            {/* Main image */}
            <img
              src={imgs[selectedImg]}
              alt={item.title || ''}
              className="max-w-[90vw] max-h-[90vh] object-contain select-none"
              onClick={e => e.stopPropagation()}
              onError={e => { e.currentTarget.style.opacity = '0.2' }}
            />

            {/* Next */}
            {imgs.length > 1 && (
              <button
                aria-label="Next image"
                className="absolute right-4 top-1/2 -translate-y-1/2 text-white text-3xl bg-black/40 hover:bg-black/70 rounded-full w-12 h-12 flex items-center justify-center transition-colors"
                onClick={e => { e.stopPropagation(); go(1) }}
              >›</button>
            )}

            {/* Counter + close */}
            <div className="absolute top-4 right-4 flex items-center gap-3">
              {imgs.length > 1 && (
                <span className="text-white/60 text-sm">{selectedImg + 1} / {imgs.length}</span>
              )}
              <button
                aria-label="Close image viewer"
                className="text-white/60 hover:text-white text-xl leading-none"
                onClick={() => setLightboxOpen(false)}
              >✕</button>
            </div>
          </div>
        )
      })()}
    </div>
  )
}

// ─── Snipe Modal ──────────────────────────────────────────────────────────────

function SnipeModal({ auction, logins, defaultSnipeSec, onClose, onSubmit }) {
  const item = auction.item || {}
  const retail = item.price || 0
  // Feature 1: pre-fill with currentBid + 1
  const currentBid = (auction.winningBid?.amount ?? 0)
  const [loginId, setLoginId]           = useState(logins[0]?.id || '')
  const [bidAmount, setBidAmount]       = useState(currentBid > 0 ? (currentBid + 1).toFixed(2) : '')
  const [snipeSec, setSnipeSec]         = useState(String(defaultSnipeSec ?? 5))
  const [submitting, setSubmitting]     = useState(false)
  const [error, setError]               = useState('')
  const overlayRef = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    const bid = parseFloat(bidAmount)
    if (!bid || bid <= 0) { setError('Enter a valid bid amount.'); return }
    if (!loginId) { setError('Select a BuyWander account.'); return }
    setSubmitting(true)
    try {
      await onSubmit({
        login_id:     loginId,
        url:          auctionUrl(auction),
        bid_amount:   bid,
        snipe_seconds: parseInt(snipeSec, 10) || 5,
      })
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to create snipe.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4"
      onClick={(e) => { if (e.target === overlayRef.current) onClose() }}
    >
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl">
        <div className="p-5 border-b border-gray-800">
          <h2 className="text-base font-semibold text-white truncate">
            Snipe: {item.title || auction.id}
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Retail ${item.price?.toFixed(2) || '—'} · Condition: {item.condition || '—'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">BuyWander Account</label>
            <select
              value={loginId}
              onChange={e => setLoginId(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue"
            >
              {logins.map(l => (
                <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Max Bid ($)</label>
            <input
              type="number" min="0.01" step="0.01" placeholder="e.g. 25.00"
              value={bidAmount} onChange={e => setBidAmount(e.target.value)} required
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue"
            />
            {/* Feature 6: smart bid suggestion */}
            {retail > 0 && (
              <p className="text-xs text-gray-500 mt-0.5">
                Suggested:{' '}
                <button
                  type="button"
                  onClick={() => setBidAmount((retail * 0.35).toFixed(2))}
                  className="text-bw-blue hover:underline"
                >
                  ${(retail * 0.35).toFixed(2)}
                </button>
                {' '}(35% of retail)
              </p>
            )}
            {currentBid > 0 && (
              <p className="text-xs text-gray-500 mt-0.5">
                Current bid: ${currentBid.toFixed(2)} — pre-filled with ${(currentBid + 1).toFixed(2)}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Snipe timing — bid this many seconds before auction ends
            </label>
            <input
              type="number" min="1" max="120"
              value={snipeSec} onChange={e => setSnipeSec(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue"
            />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 rounded bg-gray-800 hover:bg-gray-700 text-sm transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              className="flex-1 py-2 rounded bg-bw-blue hover:bg-bw-blue/85 text-sm font-medium transition-colors disabled:opacity-50">
              {submitting ? 'Adding…' : 'Add Snipe'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Bulk Snipe Modal ─────────────────────────────────────────────────────────

function BulkSnipeModal({ auctions, logins, defaultSnipeSec, onClose, onSubmit }) {
  const [loginId, setLoginId]   = useState(logins[0]?.id || '')
  const [bidAmount, setBidAmount] = useState('')
  const [snipeSec, setSnipeSec] = useState(String(defaultSnipeSec ?? 5))
  const [progress, setProgress] = useState(null) // null | { done, total, errors[] }
  const overlayRef = useRef(null)

  const done = progress && progress.done === progress.total

  async function handleSubmit(e) {
    e.preventDefault()
    const bid = parseFloat(bidAmount)
    if (!bid || bid <= 0) return
    const errors = []
    setProgress({ done: 0, total: auctions.length, errors })
    for (let i = 0; i < auctions.length; i++) {
      const a = auctions[i]
      try {
        await onSubmit({
          login_id: loginId,
          url: auctionUrl(a),
          bid_amount: bid,
          snipe_seconds: parseInt(snipeSec, 10) || 5,
        })
      } catch {
        errors.push(a.item?.title || a.id)
      }
      setProgress({ done: i + 1, total: auctions.length, errors: [...errors] })
    }
  }

  return (
    <div ref={overlayRef}
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4"
      onClick={e => { if (e.target === overlayRef.current && !progress) onClose() }}
    >
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl">
        <div className="p-5 border-b border-gray-800">
          <h2 className="text-base font-semibold">Bulk Snipe — {auctions.length} items</h2>
        </div>
        {!progress ? (
          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            <div className="max-h-28 overflow-y-auto space-y-0.5 text-xs text-gray-400">
              {auctions.map(a => (
                <div key={a.id} className="truncate">• {a.item?.title || a.id}</div>
              ))}
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Account</label>
              <select value={loginId} onChange={e => setLoginId(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
                {logins.map(l => <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Max Bid ($ — applied to all)</label>
              <input type="number" min="0.01" step="0.01" required
                value={bidAmount} onChange={e => setBidAmount(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Snipe seconds</label>
              <input type="number" min="1" max="120"
                value={snipeSec} onChange={e => setSnipeSec(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue" />
            </div>
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={onClose}
                className="flex-1 py-2 rounded bg-gray-800 hover:bg-gray-700 text-sm">Cancel</button>
              <button type="submit"
                className="flex-1 py-2 rounded bg-bw-blue hover:bg-bw-blue/85 text-sm font-medium">
                Add All Snipes
              </button>
            </div>
          </form>
        ) : (
          <div className="p-5 space-y-4">
            <div className="text-sm text-gray-300">
              {done
                ? `Done — ${progress.total - progress.errors.length} of ${progress.total} snipes added.`
                : `Adding snipes… ${progress.done} / ${progress.total}`}
            </div>
            {!done && (
              <div className="w-full bg-gray-800 rounded-full h-2">
                <div className="bg-bw-blue h-2 rounded-full transition-all"
                  style={{ width: `${(progress.done / progress.total) * 100}%` }} />
              </div>
            )}
            {progress.errors.length > 0 && (
              <p className="text-xs text-bw-red">Failed: {progress.errors.join(', ')}</p>
            )}
            {done && (
              <button onClick={onClose}
                className="w-full py-2 rounded bg-bw-blue hover:bg-bw-blue/85 text-sm font-medium">
                Done
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Browse ───────────────────────────────────────────────────────────────────

export default function Browse() {
  const { user } = useAuth()
  const uid = user?.user_id || 'anon'
  const LS_LOCATIONS     = `bw_browse_locations_${uid}`
  const LS_ENDED         = `bw_ended_auctions_${uid}`
  const LS_RECENTLY      = `bw_recently_viewed_${uid}`

  const { get, post, put, del } = useApi()

  // Accounts
  const [logins, setLogins]   = useState([])
  const [loginId, setLoginId] = useState('')

  // Locations
  const [locations, setLocations]             = useState([])
  const [selectedLocations, setSelectedLocs] = useState([])
  const [locsLoading, setLocsLoading]         = useState(false)

  // Filters
  const [search, setSearch]             = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy]             = useState('EndingSoonest')
  const [conditions, setConditions]     = useState([])
  const [quickFilters, setQuickFilters] = useState([])
  const [minPrice, setMinPrice]         = useState('')
  const [maxPrice, setMaxPrice]         = useState('')

  // Results
  const [items, setItems]           = useState([])
  const [loading, setLoading]       = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore]       = useState(false)
  const pageRef    = useRef(1)
  const sentinelRef  = useRef(null)
  const scrollerRef  = useRef(null)
  const priceCache = useRef({})  // auctionId → priceData, persists across modal open/close

  // Stable live list — updated with scroll preservation when items are removed
  const [liveItems, setLiveItems] = useState([])
  const scrollAnchorRef = useRef(null) // { id, distFromTop } captured before removal

  // Layout
  const [layout, setLayout] = useState('medium')  // 'small' | 'medium' | 'large' | 'list'

  // Mobile sidebar toggle (Feature 17)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Tab: TABS.LIVE | TABS.ENDED | TABS.RECENT
  const [activeTab, setActiveTab] = useState(TABS.LIVE)

  // Bulk selection (Feature 7)
  const [selected, setSelected]       = useState(new Set())
  const [bulkSnipeOpen, setBulkSnipeOpen] = useState(false)

  // Recently viewed (Feature 10)
  const [recentlyViewed, setRecentlyViewed] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_RECENTLY) || '[]') } catch { return [] }
  })

  // Ended-auctions cache — persisted to localStorage, pruned to 7 days
  const [endedCache, setEndedCache] = useState(() => {
    try {
      const raw = localStorage.getItem(LS_ENDED)
      if (!raw) return []
      const all = JSON.parse(raw)
      const cutoff = Date.now() - ENDED_TTL
      return all.filter(e => e.endedAt > cutoff)
    } catch { return [] }
  })

  // Ticker — forces secsLeft to recompute every second (countdown display)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [])

  // Slow ticker — drives ended-cache detection and live/ended split (every 10s is sufficient)
  const [slowTick, setSlowTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSlowTick(n => n + 1), 10_000)
    return () => clearInterval(t)
  }, [])

  // Debounce search input so API fetches don't fire on every keystroke
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  // Watchlist
  const [watchlist, setWatchlist] = useState(new Set())

  // Load watchlist on mount
  useEffect(() => {
    get('/watchlist').then(async r => {
      if (r.ok) {
        const data = await r.json()
        setWatchlist(new Set(data.map(w => w.handle)))
      }
    })
  }, [get])

  // Snipes
  const [snipes, setSnipes] = useState([])
  const snipesMap = useMemo(() => {
    const m = new Map()
    for (const s of snipes) {
      if (s.auction_uuid) m.set(s.auction_uuid, s)
      if (s.handle) m.set(s.handle, s)
    }
    return m
  }, [snipes])

  // Feature 3: Live WebSocket snipe status updates
  const handleWS = useCallback((msg) => {
    if (msg.type === 'snipe.status_changed') {
      setSnipes(prev => prev.map(s => s.id === msg.data.snipe_id ? { ...s, ...msg.data } : s))
    }
  }, [])
  useWebSocket(handleWS)

  // Feature 7: Bulk selection helpers
  const toggleSelect = useCallback((id) => {
    setSelected(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }, [])

  // Feature 10: Record a recently viewed auction (stores lightweight summary)
  const recordView = useCallback((auction) => {
    // Extract minimal data to avoid storing bloated auction objects in localStorage
    const summary = {
      id:         auction.id,
      handle:     auction.handle,
      endDate:    auction.endDate,
      url:        auction.url,
      item: {
        title:     auction.item?.title,
        price:     auction.item?.price,
        condition: auction.item?.condition,
        imageUrl:  auction.item?.imageUrl || auction.item?.thumbnailUrl || auction.item?.thumbnail,
        handle:    auction.item?.handle,
      },
      winningBid: auction.winningBid ? { amount: auction.winningBid.amount } : null,
    }
    setRecentlyViewed(prev => {
      if (prev[0]?.id === summary.id) return prev  // already most-recent, skip write
      const filtered = prev.filter(a => a.id !== summary.id)
      const next = [summary, ...filtered].slice(0, 50)
      try { localStorage.setItem(LS_RECENTLY, JSON.stringify(next)) } catch {}
      return next
    })
  }, [])

  function reloadSnipes(lid = loginId) {
    if (!lid) return
    get(`/snipes?login_id=${lid}`).then(async res => {
      if (res.ok) setSnipes(await res.json())
    })
  }

  // Modals
  const [detailTarget, setDetailTarget] = useState(null)   // auction detail modal
  const [snipeTarget, setSnipeTarget]   = useState(null)   // snipe modal (from card button)

  // Deep-link: ?open={auctionId}&login_id={loginId} — navigate here from Dashboard
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const openId = searchParams.get('open')
    if (!openId) return

    // If a login_id was provided, use it so the modal can fetch details
    const paramLoginId = searchParams.get('login_id')
    if (paramLoginId && paramLoginId !== loginId) setLoginId(paramLoginId)

    // Prefer cached data (instant); fall back to a stub so the modal fetches via API
    const fromLive = liveItems.find(a => a.id === openId)
    if (fromLive) { setDetailTarget(fromLive); setSearchParams({}, { replace: true }); return }
    const fromEnded = endedCache.find(e => e.auction?.id === openId)
    if (fromEnded) { setDetailTarget(fromEnded.auction); setSearchParams({}, { replace: true }); return }

    // Not in any cache yet — open modal with stub; AuctionDetailModal fetches full details
    setDetailTarget({ id: openId })
    setSearchParams({}, { replace: true })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])
  const [defaultSec, setDefaultSec]     = useState(5)
  const [snipeSuccess, setSnipeSuccess] = useState('')
  const [defaultLocationId, setDefaultLocationId] = useState('')

  // ── Bootstrap: load accounts + settings ───────────────────────────────────
  useEffect(() => {
    get('/logins').then(async res => {
      if (!res.ok) return
      const data = await res.json()
      setLogins(data)
      if (data.length) {
        setLoginId(data[0].id)
        reloadSnipes(data[0].id)
      }
    })
    get('/settings').then(async res => {
      if (!res.ok) return
      const cfg = await res.json()
      setDefaultSec(cfg?.defaults?.snipe_seconds ?? 5)
      setDefaultLocationId(cfg?.defaults?.default_location_id || '')
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [get])

  // ── Load locations when login changes (no defaultLocationId dep to avoid double-fetch) ──
  const defaultLocationIdRef = useRef(defaultLocationId)
  useEffect(() => { defaultLocationIdRef.current = defaultLocationId }, [defaultLocationId])

  // Tracks whether we've already applied the default location once — never apply again after that
  const defaultLocAppliedRef = useRef(false)

  useEffect(() => {
    if (!loginId) return
    setLocsLoading(true)
    get(`/auctions/locations/list?login_id=${loginId}`)
      .then(async res => {
        if (!res.ok) return
        const data = await res.json()
        const locs = Array.isArray(data) ? data : data.locations || []
        setLocations(locs)
        try {
          const saved = localStorage.getItem(LS_LOCATIONS)
          if (saved) {
            const ids = JSON.parse(saved)
            const valid = ids.filter(id => locs.some(l => l.id === id))
            setSelectedLocs(valid)
            defaultLocAppliedRef.current = true
            return
          }
        } catch {}
        // No saved selection — use default location (read via ref to avoid stale dep)
        const defId = defaultLocationIdRef.current
        if (defId && locs.some(l => l.id === defId)) {
          setSelectedLocs([defId])
          defaultLocAppliedRef.current = true
        }
      })
      .finally(() => setLocsLoading(false))
  }, [loginId, get])

  // Apply default location once settings arrive IF locations are loaded but default hasn't been applied yet
  useEffect(() => {
    if (!defaultLocationId || defaultLocAppliedRef.current || locations.length === 0) return
    if (locations.some(l => l.id === defaultLocationId)) {
      setSelectedLocs([defaultLocationId])
      defaultLocAppliedRef.current = true
    }
  }, [defaultLocationId, locations])

  // ── Detect newly-ended auctions each tick; add to ended cache ─────────────
  useEffect(() => {
    if (!items.length) return
    const now = Date.now()
    const cutoff = now - ENDED_TTL
    const newlyEnded = items.filter(a => a.endDate && new Date(a.endDate).getTime() <= now)
    if (!newlyEnded.length) return
    setEndedCache(prev => {
      const existingIds = new Set(prev.map(e => e.auction.id))
      const toAdd = newlyEnded
        .filter(a => !existingIds.has(a.id))
        .map(a => ({ auction: a, endedAt: new Date(a.endDate).getTime() }))
      if (!toAdd.length) return prev  // same ref → no re-render
      const next = [...prev.filter(e => e.endedAt > cutoff), ...toAdd]
      try { localStorage.setItem(LS_ENDED, JSON.stringify(next)) } catch {}
      return next
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slowTick, items])

  // ── Parse quoted phrases from search input ────────────────────────────────
  const { apiQuery, exactPhrases } = useMemo(() => parseSearchPhrases(debouncedSearch), [debouncedSearch])

  // ── Build search body from current filters ────────────────────────────────
  const buildBody = useCallback((pg) => ({
    login_id:           loginId,
    page:               pg,
    sort_by:            sortBy,
    search:             apiQuery,  // quotes stripped; phrase filtering is client-side
    conditions,
    store_location_ids: selectedLocations,
    min_retail_price:   minPrice ? parseFloat(minPrice) : null,
    max_retail_price:   maxPrice ? parseFloat(maxPrice) : null,
  }), [loginId, sortBy, apiQuery, conditions, selectedLocations, minPrice, maxPrice])

  // Apply quick filters + exact phrase filter client-side
  const filteredItems = useMemo(() => {
    let result = items
    // Enforce quoted phrases: title must contain each phrase as a substring
    if (exactPhrases.length) {
      result = result.filter(a => {
        const text = (a.item?.title || '').toLowerCase()
        return exactPhrases.every(p => text.includes(p))
      })
    }
    if (!quickFilters.length) return result
    return result.filter(a =>
      quickFilters.every(f => {
        const fn = QUICK_FILTER_FNS[f]
        return fn ? fn(a, snipesMap, watchlist) : true
      })
    )
  }, [items, quickFilters, snipesMap, watchlist, exactPhrases])

  // ── Maintain stable live list with scroll preservation on item removal ────
  useEffect(() => {
    const now = Date.now()
    const newLive = filteredItems.filter(a => !a.endDate || new Date(a.endDate).getTime() > now)

    setLiveItems(prev => {
      // Detect removed items
      const prevIds = new Set(prev.map(a => a.id))
      const nextIds = new Set(newLive.map(a => a.id))
      const removedIds = new Set([...prevIds].filter(id => !nextIds.has(id)))

      if (removedIds.size > 0 && scrollerRef.current) {
        // Capture first visible non-removed card as scroll anchor before update
        const scroller = scrollerRef.current
        const scrollerTop = scroller.getBoundingClientRect().top
        const cards = scroller.querySelectorAll('[data-auction-id]')
        for (const card of cards) {
          if (removedIds.has(card.dataset.auctionId)) continue
          const rect = card.getBoundingClientRect()
          if (rect.bottom > scrollerTop + 1) {
            scrollAnchorRef.current = {
              id: card.dataset.auctionId,
              distFromTop: rect.top - scrollerTop,
            }
            break
          }
        }
      }

      return newLive
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredItems, slowTick])

  // After render: restore scroll so anchor item is at the same position
  useLayoutEffect(() => {
    if (!scrollAnchorRef.current || !scrollerRef.current) return
    const { id, distFromTop } = scrollAnchorRef.current
    scrollAnchorRef.current = null
    const card = scrollerRef.current.querySelector(`[data-auction-id="${id}"]`)
    if (!card) return
    const newDist = card.getBoundingClientRect().top - scrollerRef.current.getBoundingClientRect().top
    scrollerRef.current.scrollTop += newDist - distFromTop
  }, [liveItems])

  // ── Fetch page 1, replace items (triggered by filter changes) ─────────────
  const fetchAuctions = useCallback(async () => {
    if (!loginId) return
    pageRef.current = 1
    setLoading(true)
    setHasMore(false)
    try {
      const res = await post('/auctions/search', buildBody(1))
      if (res.ok) {
        const data = await res.json()
        setItems(data.items || [])
        setHasMore((data.totalPages || 1) > 1)
      }
    } finally {
      setLoading(false)
    }
  }, [loginId, buildBody, post])

  useEffect(() => { fetchAuctions() }, [fetchAuctions])

  // ── Load next page, append items (triggered by scroll sentinel) ───────────
  const loadMore = useCallback(async () => {
    if (!hasMore || loading || loadingMore) return
    const nextPage = pageRef.current + 1
    setLoadingMore(true)
    try {
      const res = await post('/auctions/search', buildBody(nextPage))
      if (res.ok) {
        const data = await res.json()
        setItems(prev => [...prev, ...(data.items || [])])
        pageRef.current = nextPage
        setHasMore(nextPage < (data.totalPages || 1))
      }
    } finally {
      setLoadingMore(false)
    }
  }, [hasMore, loading, loadingMore, buildBody, post])

  // ── IntersectionObserver on sentinel div ──────────────────────────────────
  const loadMoreRef = useRef(loadMore)
  useEffect(() => { loadMoreRef.current = loadMore }, [loadMore])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting) loadMoreRef.current() },
      { root: scrollerRef.current, rootMargin: '200px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, []) // observer created once; loadMoreRef always holds the latest callback

  // ── Auto-continue loading when filtered results don't fill the viewport ──
  // After each page finishes, if the sentinel is still visible (items are sparse
  // after client-side filtering), immediately queue another page load.
  // Capped at 10 consecutive auto-loads to prevent fetching the entire catalog.
  const autoLoadCountRef = useRef(0)
  // Feature 12: track cap state so render can show "Load more" button
  const [capReached, setCapReached] = useState(false)

  // Reset counter on any filter/sort change (user intentional action)
  useEffect(() => {
    autoLoadCountRef.current = 0
    if (capReached) setCapReached(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quickFilters, conditions, sortBy, search, selectedLocations])

  useEffect(() => {
    if (!hasMore || loading || loadingMore) return
    if (autoLoadCountRef.current >= 10) {
      setCapReached(true)
      return // cap consecutive auto-loads
    }
    const sentinel = sentinelRef.current
    const scroller = scrollerRef.current
    if (!sentinel || !scroller) return
    const sr = sentinel.getBoundingClientRect()
    const cr = scroller.getBoundingClientRect()
    if (sr.top <= cr.bottom + 200) {
      autoLoadCountRef.current += 1
      loadMoreRef.current()
    }
  }, [filteredItems.length, hasMore, loading, loadingMore])

  // ── Helpers ────────────────────────────────────────────────────────────────
  function toggleCondition(cond) {
    setConditions(prev =>
      prev.includes(cond) ? prev.filter(c => c !== cond) : [...prev, cond]
    )
  }

  function toggleQuickFilter(val) {
    setQuickFilters(prev =>
      prev.includes(val) ? prev.filter(f => f !== val) : [...prev, val]
    )
  }

  function toggleLocation(id) {
    setSelectedLocs(prev => {
      const next = prev.includes(id) ? prev.filter(l => l !== id) : [...prev, id]
      localStorage.setItem(LS_LOCATIONS, JSON.stringify(next))
      return next
    })
  }

  function handleSearch(e) {
    e.preventDefault()
    if (activeTab === TABS.LIVE) fetchAuctions()
    // on ended tab the search state is already used to filter endedCache in render
  }

  async function handleSnipeSubmit(payload) {
    const res = await post('/snipes', payload)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to create snipe')
    }
    const label = snipeTarget?.item?.title || detailTarget?.item?.title || snipeTarget?.id || ''
    setSnipeSuccess(`Snipe added${label ? `: ${label}` : ''}`)
    setTimeout(() => setSnipeSuccess(''), 5000)
    reloadSnipes()
  }

  const handleWatchToggle = useCallback(async (handle, url, title) => {
    const res = await post('/watchlist', { url, title })
    if (res.ok) {
      setWatchlist(prev => new Set([...prev, handle]))
    }
  }, [post])

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full">

      {/* Mobile backdrop (Feature 17) */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 z-20 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ── Sidebar filters ─────────────────────────────────────────────── */}
      <aside className={`w-60 shrink-0 bg-gray-900 border-r border-gray-800 p-4 overflow-y-auto flex flex-col gap-5 md:static md:translate-x-0 md:z-auto fixed inset-y-0 left-0 z-30 transition-transform duration-200 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>

        {/* Account selector */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wide">Account</label>
          <select
            value={loginId}
            onChange={e => { setLoginId(e.target.value); reloadSnipes(e.target.value) }}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue"
          >
            {logins.map(l => (
              <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>
            ))}
          </select>
        </div>

        {/* Quick filters */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wide">Quick Filters</label>
          <div className="flex flex-col gap-1">
            {QUICK_FILTERS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => toggleQuickFilter(value)}
                className={`text-left px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                  quickFilters.includes(value)
                    ? 'bg-bw-blue text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Condition */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wide">Condition</label>
          <div className="flex flex-col gap-1">
            {CONDITIONS.map(({ value, label }) => (
              <label key={value} className="flex items-center gap-2 text-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={conditions.includes(value)}
                  onChange={() => toggleCondition(value)}
                  className="accent-bw-blue"
                />
                <span className="text-gray-300">{label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Price range */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wide">Retail Price ($)</label>
          <div className="flex gap-1.5 items-center">
            <input
              type="number" min="0" placeholder="Min"
              value={minPrice}
              onChange={e => setMinPrice(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-bw-blue"
            />
            <span className="text-gray-500 text-xs">–</span>
            <input
              type="number" min="0" placeholder="Max"
              value={maxPrice}
              onChange={e => setMaxPrice(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-bw-blue"
            />
          </div>
        </div>

        {/* Location */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wide">
            Location {locsLoading && <span className="text-gray-500">(loading…)</span>}
          </label>
          {locations.length === 0 && !locsLoading ? (
            <p className="text-xs text-gray-600">No locations available.</p>
          ) : (
            <div className="flex flex-col gap-1 max-h-48 overflow-y-auto pr-1">
              {locations.map(loc => (
                <label key={loc.id} className="flex items-center gap-2 text-xs cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={selectedLocations.includes(loc.id)}
                    onChange={() => toggleLocation(loc.id)}
                    className="accent-bw-blue"
                  />
                  <span className="text-gray-300 truncate">{loc.name}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Clear all */}
        {(conditions.length > 0 || quickFilters.length > 0 || selectedLocations.length > 0 || minPrice || maxPrice) && (
          <button
            onClick={() => {
              setConditions([])
              setQuickFilters([])
              setSelectedLocs([])
              setMinPrice('')
              setMaxPrice('')
            }}
            className="text-xs text-gray-500 hover:text-bw-red transition-colors text-left"
          >
            ✕ Clear all filters
          </button>
        )}

        {/* Mobile close button (Feature 17) */}
        <button
          onClick={() => setSidebarOpen(false)}
          className="md:hidden mt-auto text-xs text-gray-500 hover:text-white transition-colors text-left py-2"
        >✕ Close filters</button>
      </aside>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top bar: sort + search + layout toggle */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-800 bg-gray-950 flex-wrap">
          {/* Mobile sidebar toggle (Feature 17) */}
          <button
            className="md:hidden p-1.5 rounded bg-gray-800 text-gray-400 hover:text-white transition-colors shrink-0"
            onClick={() => setSidebarOpen(s => !s)}
            title="Toggle filters"
          >☰</button>
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue"
          >
            {SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <form onSubmit={handleSearch} className="flex gap-2 flex-1">
            <div className="relative flex-1 min-w-0">
              <input
                type="text" placeholder='Search auctions… (use "quotes" for exact phrase)'
                value={search} onChange={e => setSearch(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-bw-blue"
              />
              {exactPhrases.length > 0 && (
                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs bg-bw-blue/20 text-bw-blue px-1.5 py-0.5 rounded pointer-events-none">
                  phrase
                </span>
              )}
            </div>
            <button type="submit"
              className="px-3 py-1.5 bg-bw-blue rounded text-sm hover:bg-bw-blue/85 transition-colors">
              Search
            </button>
          </form>
          {snipeSuccess && (
            <span className="text-bw-green text-xs font-medium">{snipeSuccess}</span>
          )}
          {/* Layout toggle */}
          <div className="flex rounded overflow-hidden border border-gray-700 shrink-0 text-sm">
            {[
              { value: 'small',  label: 'S', title: 'Small grid'  },
              { value: 'medium', label: 'M', title: 'Medium grid' },
              { value: 'large',  label: 'L', title: 'Large grid'  },
              { value: 'list',   label: '☰', title: 'List view'   },
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => setLayout(opt.value)}
                title={opt.title}
                className={`px-2.5 py-1.5 transition-colors ${layout === opt.value ? 'bg-bw-blue text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
              >{opt.label}</button>
            ))}
          </div>
          {/* Refresh */}
          <button
            onClick={() => fetchAuctions()}
            disabled={loading}
            title="Refresh auctions"
            className="px-2.5 py-1.5 bg-gray-800 border border-gray-700 rounded text-gray-400 hover:text-white hover:bg-gray-700 transition-colors text-sm shrink-0 disabled:opacity-50"
          >↻</button>
        </div>

        {/* Live / Ended / Recent tabs */}
        {(() => {
          const liveCount   = liveItems.length
          const endedCount  = endedCache.length
          const recentCount = recentlyViewed.length
          const tabCls = active => `px-3 py-1.5 text-xs font-medium border-b-2 transition-colors mr-1 ${
            active ? 'text-white border-bw-blue' : 'text-gray-500 border-transparent hover:text-gray-300'
          }`
          return (
            <div className="flex items-center gap-0 px-5 pt-3 border-b border-gray-800">
              <button onClick={() => setActiveTab(TABS.LIVE)} className={tabCls(activeTab === TABS.LIVE)}>
                Live {!loading && <span className="text-gray-500 ml-1">({liveCount})</span>}
              </button>
              <button onClick={() => setActiveTab(TABS.ENDED)} className={tabCls(activeTab === TABS.ENDED)}>
                Ended {endedCount > 0 && <span className="text-gray-500 ml-1">({endedCount})</span>}
              </button>
              <button onClick={() => setActiveTab(TABS.RECENT)} className={tabCls(activeTab === TABS.RECENT)}>
                Recent {recentCount > 0 && <span className="text-gray-500 ml-1">({recentCount})</span>}
              </button>
            </div>
          )
        })()}

        {/* Results */}
        <div ref={scrollerRef} className="flex-1 overflow-y-auto p-5">
          {activeTab === TABS.RECENT ? (
            /* ── Recently viewed tab (Feature 10) ────────────────────────── */
            recentlyViewed.length === 0 ? (
              <div className="flex items-center justify-center h-40">
                <p className="text-gray-500 text-sm">No recently viewed auctions yet.</p>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500">Last {recentlyViewed.length} viewed auction{recentlyViewed.length !== 1 ? 's' : ''}</p>
                  <button
                    onClick={() => { setRecentlyViewed([]); localStorage.removeItem(LS_RECENTLY) }}
                    className="text-xs text-gray-500 hover:text-bw-red transition-colors"
                  >✕ Clear history</button>
                </div>
                <div className={layout !== 'list'
                  ? GRID_COLS[layout]
                  : 'rounded-lg border border-gray-800 overflow-hidden'}>
                  {layout === 'list' && (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-800/80 text-gray-400 border-b border-gray-700">
                          <th className="w-10 px-2 py-2"></th>
                          <th className="px-3 py-2 text-left font-medium">Title</th>
                          <th className="px-3 py-2 text-left font-medium whitespace-nowrap">Condition</th>
                          <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Bid</th>
                          <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Retail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentlyViewed.map((ra, idx) => {
                          const item   = ra.item || {}
                          const wb     = ra.winningBid || {}
                          const imgUrl = getItemImage(item)
                          return (
                            <tr key={ra.id}
                              onClick={() => { setDetailTarget(ra); recordView(ra) }}
                              className={`border-b border-gray-800/60 hover:bg-gray-800/50 cursor-pointer transition-colors ${idx % 2 === 0 ? '' : 'bg-gray-900/30'}`}>
                              <td className="px-2 py-1.5">
                                {imgUrl ? <img src={imgUrl} alt="" className="w-8 h-8 object-cover rounded bg-gray-700" loading="lazy" onError={e => { e.currentTarget.style.display = 'none' }} />
                                  : <div className="w-8 h-8 rounded bg-gray-700" />}
                              </td>
                              <td className="px-3 py-1.5 text-white font-medium max-w-xs"><span className="line-clamp-2">{item.title || '(Untitled)'}</span></td>
                              <td className="px-3 py-1.5"><ConditionBadge condition={item.condition} /></td>
                              <td className="px-3 py-1.5 text-right font-mono text-white">{wb.amount ? `$${wb.amount.toFixed(2)}` : '—'}</td>
                              <td className="px-3 py-1.5 text-right font-mono text-gray-400">{item.price ? `$${item.price.toFixed(2)}` : '—'}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                  {layout !== 'list' && recentlyViewed.map(ra => {
                    const item   = ra.item || {}
                    const wb     = ra.winningBid || {}
                    const imgUrl = getItemImage(item)
                    const secsLeft = ra.endDate ? (new Date(ra.endDate) - Date.now()) / 1000 : null
                    const isEnded  = secsLeft !== null && secsLeft <= 0
                    return (
                      <div key={ra.id}
                        onClick={() => { setDetailTarget(ra); recordView(ra) }}
                        className={`bg-gray-800/60 rounded-lg flex flex-col hover:bg-gray-750 transition-colors cursor-pointer overflow-hidden border border-gray-700/30 ${isEnded ? 'opacity-60' : ''}`}>
                        {imgUrl
                          ? <div className={`w-full ${IMG_H[layout]} bg-gray-950 flex items-center justify-center overflow-hidden`}>
                              <img src={imgUrl} alt={item.title || ''} className={`max-w-full ${IMG_MAXH[layout]} object-contain`} loading="lazy" onError={e => { e.currentTarget.parentElement.style.display = 'none' }} />
                            </div>
                          : <div className={`w-full ${IMG_H[layout]} bg-gray-800 flex items-center justify-center text-gray-600 text-2xl`}>⬜</div>
                        }
                        <div className="p-3 flex flex-col flex-1">
                          <h3 className="text-base font-medium text-white leading-snug mb-2 line-clamp-2 flex-1">{item.title || '(Untitled)'}</h3>
                          <div className="space-y-0.5 text-xs text-gray-400 mb-2">
                            <div className="flex justify-between"><span>Bid</span><span className="text-white">{wb.amount ? `$${wb.amount.toFixed(2)}` : '—'}</span></div>
                            {item.condition && <div><ConditionBadge condition={item.condition} /></div>}
                          </div>
                          <div className="mt-auto w-full py-1.5 bg-gray-700 text-gray-400 rounded text-xs font-medium text-center">
                            {isEnded ? 'Ended' : secsLeft != null ? fmtSecs(secsLeft) + ' left' : 'View'}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          ) : activeTab === TABS.ENDED ? (
            /* ── Ended auctions tab ───────────────────────────────────────── */
            endedCache.length === 0 ? (
              <div className="flex items-center justify-center h-40">
                <p className="text-gray-500 text-sm">No ended auctions in the past 7 days.</p>
              </div>
            ) : (
              <div className={layout !== 'list'
                ? GRID_COLS[layout]
                : 'rounded-lg border border-gray-800 overflow-hidden'}>
                {layout === 'list' && (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-gray-800/80 text-gray-400 border-b border-gray-700">
                        <th className="w-10 px-2 py-2"></th>
                        <th className="px-3 py-2 text-left font-medium">Title</th>
                        <th className="px-3 py-2 text-right font-medium">Final Bid</th>
                        <th className="px-3 py-2 text-right font-medium">Retail</th>
                        <th className="px-3 py-2 text-right font-medium">Ended</th>
                        <th className="px-2 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...endedCache].filter(e => !search || (e.auction.item?.title || '').toLowerCase().includes(search.toLowerCase())).sort((a, b) => b.endedAt - a.endedAt).map(({ auction: ea }, idx) => {
                        const item = ea.item || {}
                        const wb = ea.winningBid || {}
                        const bidAmt = wb.amount || 0
                        const retail = item.price || 0
                        const imgUrl = getItemImage(item)
                        return (
                          <tr key={ea.id} onClick={() => { setDetailTarget(ea); recordView(ea) }}
                            className={`border-b border-gray-800/60 hover:bg-gray-800/50 cursor-pointer transition-colors ${idx % 2 === 0 ? '' : 'bg-gray-900/30'}`}>
                            <td className="px-2 py-1.5">
                              {imgUrl ? <img src={imgUrl} alt="" className="w-8 h-8 object-cover rounded bg-gray-700 opacity-60" loading="lazy" onError={e => { e.currentTarget.style.display = 'none' }} />
                                : <div className="w-8 h-8 rounded bg-gray-700" />}
                            </td>
                            <td className="px-3 py-1.5 text-gray-400 max-w-xs"><span className="line-clamp-2">{item.title || '(Untitled)'}</span></td>
                            <td className="px-3 py-1.5 text-right font-mono text-gray-400">{bidAmt ? `$${bidAmt.toFixed(2)}` : '—'}</td>
                            <td className="px-3 py-1.5 text-right font-mono text-gray-500">{retail ? `$${retail.toFixed(2)}` : '—'}</td>
                            <td className="px-3 py-1.5 text-right text-gray-500 whitespace-nowrap text-xs">
                              {new Date(ea.endDate).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                            </td>
                            {/* Feature 13: Find Similar */}
                            <td className="px-2 py-1.5">
                              <button
                                onClick={e => {
                                  e.stopPropagation()
                                  const words = (ea.item?.title || '').split(/\s+/).slice(0, 3).join(' ')
                                  setSearch(words)
                                  setActiveTab(TABS.LIVE)
                                }}
                                className="text-xs text-bw-blue hover:text-bw-blue/80 transition-colors whitespace-nowrap"
                              >
                                Find Similar →
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
                {layout !== 'list' && [...endedCache].filter(e => !search || (e.auction.item?.title || '').toLowerCase().includes(search.toLowerCase())).sort((a, b) => b.endedAt - a.endedAt).map(({ auction: ea }) => {
                  const item = ea.item || {}
                  const wb = ea.winningBid || {}
                  const bidAmt = wb.amount || 0
                  const retail = item.price || 0
                  const imgUrl = getItemImage(item)
                  return (
                    <div key={ea.id} onClick={() => { setDetailTarget(ea); recordView(ea) }}
                      className="bg-gray-800/60 rounded-lg flex flex-col hover:bg-gray-750 transition-colors cursor-pointer overflow-hidden border border-gray-700/30 opacity-75">
                      {imgUrl
                        ? <div className={`w-full ${IMG_H[layout]} bg-gray-950 flex items-center justify-center overflow-hidden`}>
                            <img src={imgUrl} alt={item.title || ''} className={`max-w-full ${IMG_MAXH[layout]} object-contain grayscale`} loading="lazy" onError={e => { e.currentTarget.parentElement.style.display = 'none' }} />
                          </div>
                        : <div className={`w-full ${IMG_H[layout]} bg-gray-800 flex items-center justify-center text-gray-600 text-2xl`}>⬜</div>
                      }
                      <div className="p-3 flex flex-col flex-1">
                        <h3 className="text-base font-medium text-gray-400 leading-snug mb-2 line-clamp-2 flex-1">{item.title || '(Untitled)'}</h3>
                        <div className="space-y-0.5 text-xs text-gray-500 mb-2">
                          <div className="flex justify-between"><span>Final bid</span><span>{bidAmt ? `$${bidAmt.toFixed(2)}` : '—'}</span></div>
                          <div className="flex justify-between"><span>Retail</span><span>{retail ? `$${retail.toFixed(2)}` : '—'}</span></div>
                        </div>
                        <div className="mt-auto w-full py-1.5 bg-gray-700 text-gray-500 rounded text-xs font-medium text-center">Ended</div>
                        {/* Feature 13: Find Similar */}
                        <button
                          onClick={e => {
                            e.stopPropagation()
                            const words = (ea.item?.title || '').split(/\s+/).slice(0, 3).join(' ')
                            setSearch(words)
                            setActiveTab(TABS.LIVE)
                          }}
                          className="text-xs text-bw-blue hover:text-bw-blue/80 transition-colors mt-1 text-center w-full"
                        >
                          Find Similar →
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )
          ) : loading ? (
            <div className="flex items-center justify-center h-40">
              <p className="text-gray-400 text-sm">Loading auctions…</p>
            </div>
          ) : liveItems.length === 0 ? (
            <div className="flex items-center justify-center h-40">
              <p className="text-gray-500 text-sm">No auctions found. Try adjusting your filters.</p>
            </div>
          ) : layout !== 'list' ? (
            /* ── Grid layout (small / medium / large) ────────────────────── */
            <div className={GRID_COLS[layout]}>
              {liveItems.map(auction => {
                const item     = auction.item || {}
                const wb       = auction.winningBid || {}
                const endDate  = auction.endDate
                const secsLeft = endDate ? (new Date(endDate) - Date.now()) / 1000 : null
                const retail   = item.price || 0
                const bidAmt   = wb.amount || 0
                const offPct   = retail && bidAmt ? Math.round(100 * (1 - bidAmt / retail)) : null
                const imgUrl   = getItemImage(item)

                const cardSnipe = snipesMap.get(auction.id) || snipesMap.get(auction.handle)
                const bidCount = auction.bidCount ?? auction.numberOfBids ?? auction.bid_count ?? 0
                return (
                  <div
                    key={auction.id}
                    data-auction-id={auction.id}
                    className="bg-gray-800 rounded-lg flex flex-col hover:bg-gray-750 transition-colors cursor-pointer overflow-hidden border border-gray-700/50 relative"
                    onClick={() => { setDetailTarget(auction); recordView(auction) }}
                  >
                    {/* Bulk select checkbox (Feature 7) */}
                    <div className="absolute top-2 right-2 z-10" onClick={e => e.stopPropagation()}>
                      <input type="checkbox"
                        checked={selected.has(auction.id)}
                        onChange={() => toggleSelect(auction.id)}
                        className="w-4 h-4 accent-bw-blue" />
                    </div>
                    {cardSnipe && (
                      <div className="absolute top-2 left-2 z-10 bg-bw-blue text-white text-xs px-1.5 py-0.5 rounded-full font-medium flex items-center gap-1 shadow">
                        ⚡ Sniped ${cardSnipe.bid_amount.toFixed(2)}
                      </div>
                    )}
                    {/* Photo */}
                    {imgUrl ? (
                      <div className={`w-full ${IMG_H[layout]} bg-gray-950 flex items-center justify-center overflow-hidden`}>
                        <img
                          src={imgUrl}
                          alt={item.title || ''}
                          className={`max-w-full ${IMG_MAXH[layout]} object-contain`}
                          loading="lazy"
                          onError={e => { e.currentTarget.parentElement.style.display = 'none' }}
                        />
                      </div>
                    ) : (
                      <div className={`w-full ${IMG_H[layout]} bg-gray-800 flex items-center justify-center text-gray-600 text-2xl`}>⬜</div>
                    )}

                    <div className="p-3 flex flex-col flex-1">
                      {/* Title */}
                      <h3 className="text-base font-medium text-gray-300 leading-snug mb-2 line-clamp-2 flex-1">
                        {item.title || '(Untitled)'}
                      </h3>

                      {/* Key stats: bid + time */}
                      <div className="flex items-end justify-between mb-2">
                        <div>
                          <div className="text-base font-bold text-white tabular-nums leading-none">
                            {bidAmt ? `$${bidAmt.toFixed(2)}` : '—'}
                          </div>
                          {retail > 0 && offPct != null && (
                            <div className="text-xs text-bw-green mt-0.5">{offPct}% off retail</div>
                          )}
                        </div>
                        {secsLeft != null && (
                          <div className={`text-right ${secsLeft < 300 ? 'text-bw-yellow' : 'text-gray-400'}`}>
                            <div className={`text-sm font-semibold tabular-nums leading-none ${secsLeft < 300 ? 'text-bw-yellow' : 'text-gray-300'}`}>
                              {fmtSecs(secsLeft)}
                            </div>
                            <div className="text-xs mt-0.5 text-gray-500">left</div>
                          </div>
                        )}
                      </div>

                      {/* Supporting details */}
                      <div className="flex items-center justify-between mb-3 text-xs text-gray-500">
                        {item.condition && <ConditionBadge condition={item.condition} />}
                        <div className="flex items-center gap-1 ml-auto">
                          <BidCountBadge count={bidCount} />
                          {auction.storeLocation && (
                            <span className="truncate max-w-[80px]">{auction.storeLocation.name}</span>
                          )}
                        </div>
                      </div>

                      {(() => {
                        const isEnded = secsLeft !== null && secsLeft <= 0
                        return (
                          <button
                            onClick={e => { e.stopPropagation(); if (!isEnded) setSnipeTarget(auction) }}
                            disabled={isEnded}
                            className={`mt-auto w-full py-1.5 rounded text-xs font-semibold transition-colors ${
                              isEnded
                                ? 'bg-gray-700/50 text-gray-600 cursor-not-allowed'
                                : 'bg-bw-blue text-white hover:bg-bw-blue/85'
                            }`}
                          >
                            {isEnded ? 'Ended' : 'Snipe This'}
                          </button>
                        )
                      })()}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            /* ── List layout ─────────────────────────────────────────────── */
            <div className="rounded-lg border border-gray-800 overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-800/80 text-gray-400 border-b border-gray-700">
                    <th className="w-8 px-2 py-2"></th>
                    <th className="w-10 px-2 py-2"></th>
                    <th className="px-3 py-2 text-left font-medium">Title</th>
                    <th className="px-3 py-2 text-left font-medium whitespace-nowrap">Condition</th>
                    <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Bid</th>
                    <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Retail</th>
                    <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Off%</th>
                    <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Time Left</th>
                    <th className="px-3 py-2 text-left font-medium whitespace-nowrap">Location</th>
                    <th className="px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {liveItems.map((auction, idx) => {
                    const item     = auction.item || {}
                    const wb       = auction.winningBid || {}
                    const endDate  = auction.endDate
                    const secsLeft = endDate ? (new Date(endDate) - Date.now()) / 1000 : null
                    const retail   = item.price || 0
                    const bidAmt   = wb.amount || 0
                    const offPct   = retail && bidAmt ? Math.round(100 * (1 - bidAmt / retail)) : null
                    const imgUrl   = getItemImage(item)
                    const loc      = auction.storeLocation
                    const locStr   = loc ? ([loc.city, loc.state].filter(Boolean).join(', ') || loc.name || '') : ''
                    const rowSnipe = snipesMap.get(auction.id) || snipesMap.get(auction.handle)
                    const bidCount = auction.bidCount ?? auction.numberOfBids ?? auction.bid_count ?? 0

                    return (
                      <tr
                        key={auction.id}
                        data-auction-id={auction.id}
                        className={`border-b border-gray-800/60 hover:bg-gray-800/50 cursor-pointer transition-colors ${idx % 2 === 0 ? '' : 'bg-gray-900/30'}`}
                        onClick={() => { setDetailTarget(auction); recordView(auction) }}
                      >
                        {/* Bulk select checkbox (Feature 7) */}
                        <td className="px-2 py-1.5" onClick={e => e.stopPropagation()}>
                          <input type="checkbox"
                            checked={selected.has(auction.id)}
                            onChange={() => toggleSelect(auction.id)}
                            className="w-4 h-4 accent-bw-blue" />
                        </td>
                        {/* Thumbnail */}
                        <td className="px-2 py-1.5">
                          {imgUrl ? (
                            <img
                              src={imgUrl}
                              alt=""
                              className="w-8 h-8 object-cover rounded bg-gray-700"
                              loading="lazy"
                              onError={e => { e.currentTarget.style.display = 'none' }}
                            />
                          ) : (
                            <div className="w-8 h-8 rounded bg-gray-700" />
                          )}
                        </td>
                        {/* Title */}
                        <td className="px-3 py-1.5 text-white font-medium max-w-xs">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="line-clamp-2 leading-snug">{item.title || '(Untitled)'}</span>
                            {rowSnipe && (
                              <span className="shrink-0 bg-bw-blue/20 text-bw-blue text-xs px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap">
                                ⚡ ${rowSnipe.bid_amount.toFixed(2)}
                              </span>
                            )}
                          </div>
                        </td>
                        {/* Condition */}
                        <td className="px-3 py-1.5 whitespace-nowrap"><ConditionBadge condition={item.condition} /></td>
                        {/* Bid */}
                        <td className="px-3 py-1.5 text-right font-mono font-semibold text-white whitespace-nowrap">
                          <span className="flex items-center justify-end gap-1">
                            {bidAmt ? `$${bidAmt.toFixed(2)}` : '—'}
                            <BidCountBadge count={bidCount} />
                          </span>
                        </td>
                        {/* Retail */}
                        <td className="px-3 py-1.5 text-right font-mono text-gray-400 whitespace-nowrap">
                          {retail ? `$${retail.toFixed(2)}` : '—'}
                        </td>
                        {/* Off% */}
                        <td className="px-3 py-1.5 text-right whitespace-nowrap">
                          {offPct != null ? (
                            <span className="text-bw-green font-medium">{offPct}%</span>
                          ) : '—'}
                        </td>
                        {/* Time left */}
                        <td className={`px-3 py-1.5 text-right font-mono whitespace-nowrap ${secsLeft != null && secsLeft < 300 ? 'text-bw-yellow' : 'text-gray-400'}`}>
                          {secsLeft != null ? fmtSecs(secsLeft) : '—'}
                        </td>
                        {/* Location */}
                        <td className="px-3 py-1.5 text-gray-400 whitespace-nowrap max-w-[120px] truncate">{locStr || '—'}</td>
                        {/* Snipe button */}
                        <td className="px-2 py-1.5">
                          <button
                            onClick={e => { e.stopPropagation(); setSnipeTarget(auction) }}
                            className="px-2.5 py-1 bg-bw-blue/20 hover:bg-bw-blue/50 text-bw-blue rounded text-xs font-medium transition-colors whitespace-nowrap"
                          >
                            Snipe
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="py-3 flex justify-center">
            {loadingMore && <span className="text-gray-500 text-xs">Loading more…</span>}
            {!loadingMore && !hasMore && items.length > 0 && (
              <span className="text-gray-600 text-xs">— End of results —</span>
            )}
            {/* Feature 12: "Load more" button when auto-load cap is reached */}
            {!loadingMore && hasMore && capReached && (
              <button
                onClick={() => {
                  setCapReached(false)
                  autoLoadCountRef.current = 0
                  loadMoreRef.current()
                }}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-sm text-gray-300 transition-colors"
              >
                Load more results
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Auction detail modal (click on card) ─────────────────────────── */}
      {detailTarget && (
        <AuctionDetailModal
          auction={detailTarget}
          loginId={loginId}
          logins={logins}
          defaultSnipeSec={defaultSec}
          priceCache={priceCache}
          onClose={() => setDetailTarget(null)}
          snipe={snipesMap.get(detailTarget.id) || snipesMap.get(detailTarget.handle) || null}
          watchlist={watchlist}
          onWatchToggle={handleWatchToggle}
          onSnipeCancel={async id => {
            const res = await del(`/snipes/${id}`)
            if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Failed') }
            reloadSnipes()
          }}
          onSnipeUpdate={async (id, updates) => {
            const res = await put(`/snipes/${id}`, updates)
            if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Failed') }
            reloadSnipes()
          }}
          onSnipe={async payload => {
            const res = await post('/snipes', payload)
            if (!res.ok) {
              const err = await res.json().catch(() => ({}))
              throw new Error(err.detail || 'Failed to create snipe')
            }
            setSnipeSuccess(`Snipe added: ${detailTarget?.item?.title || detailTarget?.id || ''}`)
            setTimeout(() => setSnipeSuccess(''), 5000)
            reloadSnipes()
          }}
        />
      )}

      {/* ── Snipe modal (from card "Snipe This" button) ───────────────────── */}
      {snipeTarget && (
        <SnipeModal
          auction={snipeTarget}
          logins={logins}
          defaultSnipeSec={defaultSec}
          onClose={() => setSnipeTarget(null)}
          onSubmit={handleSnipeSubmit}
        />
      )}

      {/* ── Bulk snipe modal (Feature 7) ──────────────────────────────────── */}
      {bulkSnipeOpen && (
        <BulkSnipeModal
          auctions={liveItems.filter(a => selected.has(a.id))}
          logins={logins}
          defaultSnipeSec={defaultSec}
          onClose={() => { setBulkSnipeOpen(false); setSelected(new Set()) }}
          onSubmit={handleSnipeSubmit}
        />
      )}

      {/* ── Bulk action bar (Feature 7) — sticky when items are selected ─── */}
      {selected.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-gray-900/95 backdrop-blur border-t border-gray-700 px-5 py-3 flex items-center gap-3 z-20 shadow-2xl">
          <span className="text-sm text-gray-300 font-medium">{selected.size} selected</span>
          <button
            onClick={() => setBulkSnipeOpen(true)}
            className="px-4 py-1.5 bg-bw-blue rounded text-sm hover:bg-bw-blue/85 font-medium transition-colors"
          >⚡ Snipe Selected</button>
          <button
            onClick={() => setSelected(new Set())}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm transition-colors"
          >Clear</button>
        </div>
      )}
    </div>
  )
}
