import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi, fmtApiError } from '../hooks/useApi'

// Today as YYYY-MM-DD
function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function fmtDateShort(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
    })
  } catch {
    return iso
  }
}

export default function Cart() {
  const { get, post, put, del } = useApi()
  const [logins, setLogins]           = useState([])
  const [loginId, setLoginId]         = useState('')
  const [locations, setLocations]     = useState([])
  const [locationId, setLocationId]   = useState('')
  const [defaultLocationId, setDefaultLocationId] = useState('')
  // True once the user has manually chosen a location — at that point we stop
  // auto-applying the settings default so we don't override their choice.
  const userPickedLocationRef = useRef(false)
  const locationsRef = useRef([])
  const defaultLocationIdRef = useRef('')
  const [cartData, setCartData]         = useState(null)
  const [reserved, setReserved]         = useState([])
  const [payMethods, setPayMethods]     = useState([])
  const [removalStatus, setRemovalStatus] = useState(null)  // { allowedRemovals, usedRemovals, remainingRemovals, feeAmount }
  const [loading, setLoading]           = useState(false)
  const [msg, setMsg]                   = useState('')
  const [payMsg, setPayMsg]             = useState('')
  const [paying, setPaying]             = useState(false)

  // Appointment scheduling state
  const [scheduleOpen, setScheduleOpen]   = useState(false)
  const [scheduleDay, setScheduleDay]     = useState(todayStr())
  const [availSlots, setAvailSlots]       = useState([])
  const [slotsLoading, setSlotsLoading]   = useState(false)
  const [slotsError, setSlotsError]       = useState('')
  const [scheduling, setScheduling]       = useState(false)
  const [cancellingAppt, setCancellingAppt] = useState(false)

  // Keep the ref in sync so the locations effect can read it without a dep
  useEffect(() => { defaultLocationIdRef.current = defaultLocationId }, [defaultLocationId])

  // Load settings (for default location) and logins in parallel on mount
  useEffect(() => {
    get('/settings').then(async res => {
      if (!res.ok) return
      const cfg = await res.json()
      setDefaultLocationId(cfg?.defaults?.default_location_id || '')
    })
    get('/logins').then(async res => {
      if (!res.ok) return
      const data = await res.json()
      setLogins(data)
      if (data.length > 0) setLoginId(data[0].id)
    })
  }, [get])

  // Load locations whenever loginId changes
  useEffect(() => {
    if (!loginId) return
    userPickedLocationRef.current = false  // reset on account switch
    get(`/auctions/locations/list?login_id=${loginId}`).then(async res => {
      if (!res.ok) return
      const locs = await res.json()
      locationsRef.current = locs
      setLocations(locs)
      // Pick the settings default if it's in the list, otherwise first location.
      // Reading via ref so this works even if settings loaded before locations.
      const defId = defaultLocationIdRef.current
      const initial = (defId && locs.find(l => (l.id || l.storeLocationId) === defId))
        ? defId
        : (locs[0]?.id || locs[0]?.storeLocationId || '')
      setLocationId(initial)
    })
  }, [loginId, get])

  // When the settings default location is known and the user hasn't manually
  // picked a location yet, switch to it (handles the race where settings
  // arrive after locations).
  useEffect(() => {
    if (!defaultLocationId || userPickedLocationRef.current) return
    const locs = locationsRef.current
    const match = locs.find(l => (l.id || l.storeLocationId) === defaultLocationId)
    if (match) setLocationId(defaultLocationId)
  }, [defaultLocationId])

  const loadCart = useCallback(async () => {
    if (!loginId || !locationId) return
    setLoading(true)
    setMsg('')
    try {
      const [cartRes, removalRes] = await Promise.all([
        get(`/cart/${loginId}?store_location_id=${locationId}`),
        get(`/cart/${loginId}/removal-status?store_location_id=${locationId}`),
      ])
      if (cartRes.ok) {
        const data = await cartRes.json()
        setCartData(data.cart_data)
        setReserved(data.reserved || [])
        setPayMethods(data.methods || [])
      } else {
        setMsg('Failed to load cart.')
      }
      if (removalRes.ok) setRemovalStatus(await removalRes.json())
    } finally {
      setLoading(false)
    }
  }, [loginId, locationId, get])

  useEffect(() => { loadCart() }, [loadCart])

  async function handlePay() {
    if (!loginId || !locationId) return
    setPaying(true)
    setPayMsg('')
    try {
      const res = await post(`/cart/${loginId}/pay`, { store_location_id: locationId })
      const body = await res.json().catch(() => ({}))
      console.log('[pay]', res.status, body)
      if (res.ok) {
        await loadCart()
        const conf = body.confirmationNumber || body.orderId
        const msg = conf
          ? `✓ Payment successful! Confirmation #${conf}. Items moved to "Paid Items Awaiting Pickup".`
          : body.chargeConfirmed
          ? '✓ Card charged successfully. BuyWander is processing your order — items will appear in "Paid Items Awaiting Pickup" shortly.'
          : '✓ Payment successful! Items moved to "Paid Items Awaiting Pickup".'
        setPayMsg(msg)
      } else {
        setPayMsg(fmtApiError(body, 'Payment failed.'))
      }
    } catch (e) {
      console.error('[pay] error', e)
      setPayMsg('Network error — please try again.')
    } finally {
      setPaying(false)
    }
  }

  async function handleRemoveItem(auctionId, title) {
    const rs = removalStatus
    let confirmMsg = `Remove "${title || 'this item'}" from your cart?`
    if (rs) {
      if (rs.remainingRemovals > 0) {
        confirmMsg += `\n\n${rs.remainingRemovals} free removal${rs.remainingRemovals !== 1 ? 's' : ''} remaining (${rs.usedRemovals} of ${rs.allowedRemovals} used).`
      } else {
        const fee = rs.feeAmount ? `$${rs.feeAmount.toFixed(2)}` : 'a fee'
        confirmMsg += `\n\n⚠️ No free removals left (${rs.usedRemovals} of ${rs.allowedRemovals} used). This removal may incur ${fee}.`
      }
    }
    if (!window.confirm(confirmMsg)) return
    setMsg('')
    const res = await del(`/cart/${loginId}/items`, {
      auction_id: auctionId, reason: 'UserRemoval', notes: '',
    })
    if (res.ok) {
      setMsg('Item removed.')
      await loadCart()
    } else {
      setMsg('Failed to remove item.')
    }
  }

  async function handleFetchSlots() {
    if (!loginId || !locationId || !scheduleDay) return
    setSlotsLoading(true)
    setSlotsError('')
    setAvailSlots([])
    try {
      const res = await get(
        `/cart/${loginId}/open-slots?location_id=${locationId}&day=${scheduleDay}`
      )
      if (res.ok) {
        const data = await res.json()
        const slots = (Array.isArray(data) ? data : data.slots || [])
          .filter(s => s.isAvailable !== false)
        setAvailSlots(slots)
        if (slots.length === 0) setSlotsError('No available slots on that day.')
      } else {
        setSlotsError('Failed to load available slots.')
      }
    } catch {
      setSlotsError('Network error loading slots.')
    } finally {
      setSlotsLoading(false)
    }
  }

  async function handleSchedule(slotDateIso) {
    setScheduling(true)
    setMsg('')
    try {
      let res
      if (activeVisit) {
        res = await put(`/cart/${loginId}/appointments/${activeVisit.id}`, { new_date_iso: slotDateIso })
      } else {
        res = await post(`/cart/${loginId}/appointments`, {
          location_id:    locationId,
          visit_date_iso: slotDateIso,
        })
      }
      if (res.ok) {
        setMsg(activeVisit ? 'Appointment rescheduled!' : 'Pickup appointment scheduled!')
        setScheduleOpen(false)
        setAvailSlots([])
        await loadCart()
      } else {
        const err = await res.json().catch(() => ({}))
        setMsg(fmtApiError(err, 'Failed to schedule appointment.'))
      }
    } finally {
      setScheduling(false)
    }
  }

  async function handleCancelAppointment(visitId, visitDate) {
    setCancellingAppt(true)
    setMsg('')
    try {
      const res = await del(
        `/cart/${loginId}/appointments/${visitId}?visit_date=${encodeURIComponent(visitDate)}`
      )
      if (res.ok) {
        setMsg('Appointment cancelled.')
        await loadCart()
      } else {
        const err = await res.json().catch(() => ({}))
        setMsg(fmtApiError(err, 'Failed to cancel appointment.'))
      }
    } finally {
      setCancellingAppt(false)
    }
  }

  // ── Derived data ───────────────────────────────────────────────────────────
  const visits    = cartData?.visits    || cartData?.Visits    || []
  const paidItems = cartData?.paidItems || cartData?.PaidItems || []
  // `reserved` items are won-but-unpaid auctions — these are the actual "cart" items needing payment
  const cartItems = reserved

  // Active pickup appointment
  const activeVisit = visits.find(v => v.status === 'Booked')

  // Items expiring within 48 hours
  const FORTY_EIGHT_HOURS = 48 * 60 * 60 * 1000
  const expiringItems = cartItems.filter(item => {
    const deadline = item.endDate || item.reservedUntil || item.expiresAt
    if (!deadline) return false
    const ms = new Date(deadline).getTime() - Date.now()
    return ms > 0 && ms <= FORTY_EIGHT_HOURS
  })

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-6 space-y-8">

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <label className="sr-only" htmlFor="cart-account">Account</label>
        <select
          id="cart-account"
          value={loginId}
          onChange={e => setLoginId(e.target.value)}
          disabled={loading || paying}
          className="field w-auto"
        >
          {logins.map(l => (
            <option key={l.id} value={l.id}>{l.display_name || l.bw_email}</option>
          ))}
        </select>
        <label className="sr-only" htmlFor="cart-location">Location</label>
        <select
          id="cart-location"
          value={locationId}
          onChange={e => { userPickedLocationRef.current = true; setLocationId(e.target.value) }}
          disabled={loading || paying}
          className="field w-auto"
        >
          {locations.map(loc => (
            <option key={loc.id || loc.storeLocationId} value={loc.id || loc.storeLocationId}>
              {loc.name || loc.storeLocationName || loc.id}
            </option>
          ))}
        </select>
        <button
          onClick={loadCart}
          disabled={loading}
          className="btn btn-primary"
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {msg && (
        <div className="bg-gray-800 border border-gray-700 rounded px-4 py-2 text-sm">{msg}</div>
      )}
      {payMsg && (
        <div className={`rounded px-4 py-2 text-sm font-medium ${payMsg.startsWith('✓') ? 'bg-bw-green/10 border border-bw-green/30 text-bw-green' : 'bg-bw-red/10 border border-bw-red/30 text-bw-red'}`}>
          {payMsg}
        </div>
      )}

      {/* Removal allowance banner */}
      {removalStatus && (() => {
        const { allowedRemovals, usedRemovals, remainingRemovals, feeAmount } = removalStatus
        const pct = allowedRemovals > 0 ? usedRemovals / allowedRemovals : 1
        const color = remainingRemovals === 0
          ? 'border-bw-red/40 bg-bw-red/10 text-bw-red'
          : pct >= 0.7
          ? 'border-bw-yellow/40 bg-bw-yellow/10 text-bw-yellow'
          : 'border-gray-700 bg-gray-800/50 text-gray-400'
        return (
          <div className={`border rounded px-4 py-2 text-xs flex items-center gap-3 ${color}`}>
            <span className="font-medium">Cart Removals:</span>
            <span>{remainingRemovals} of {allowedRemovals} free remaining</span>
            <span className="text-gray-500">({usedRemovals} used)</span>
            {remainingRemovals === 0 && feeAmount > 0 && (
              <span className="ml-auto">Fee per removal: ${feeAmount.toFixed(2)}</span>
            )}
          </div>
        )
      })()}

      {expiringItems.length > 0 && (
        <div className="bg-bw-yellow/10 border border-bw-yellow/30 rounded-lg px-4 py-3 flex items-start gap-3">
          <span className="text-bw-yellow text-lg shrink-0">⚠</span>
          <div>
            <p className="text-bw-yellow text-sm font-medium">
              {expiringItems.length === 1
                ? '1 cart item expires within 48 hours'
                : `${expiringItems.length} cart items expire within 48 hours`}
            </p>
            <ul className="mt-1 space-y-0.5">
              {expiringItems.map((item, idx) => {
                const auctionId = item.auctionId || item.auction_id || item.id
                const title = item.item?.title || item.title || item.itemTitle || item.handle || item.name || 'Unknown item'
                const deadline = item.endDate || item.reservedUntil || item.expiresAt
                const hoursLeft = Math.floor((new Date(deadline).getTime() - Date.now()) / 3600000)
                return (
                  <li key={auctionId || idx} className="text-bw-yellow/80 text-xs">
                    {title} — {hoursLeft}h remaining
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
      )}

      {loading && !cartData ? (
        <p className="text-gray-400">Loading cart...</p>
      ) : (
        <>
          {/* ── Paid Items Awaiting Pickup ─────────────────────────────────── */}
          <section>
            <h2 className="text-lg font-semibold mb-3">
              Paid Items Awaiting Pickup
              {paidItems.length > 0 && (
                <span className="ml-2 text-sm font-normal text-gray-400">({paidItems.length})</span>
              )}
            </h2>
            {paidItems.length === 0 ? (
              <p className="text-gray-500 text-sm">No paid items awaiting pickup.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-800">
                <table className="mat-table text-left">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>SKU</th>
                      <th>Location</th>
                      <th>Paid</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paidItems.map((item, idx) => {
                      const title  = item.title || item.itemTitle || 'Unknown'
                      const sku    = item.bwsku || item.sku || '—'
                      const loc    = (item.currentLocation || {}).description
                              || (item.currentLocation || {}).name || '—'
                      const paidAt = item.paidAt
                      return (
                        <tr key={item.id || idx}>
                          <td className="text-bw-green max-w-xs truncate font-medium">
                            {title}
                          </td>
                          <td className="font-mono text-xs">{sku}</td>
                          <td>{loc}</td>
                          <td className="whitespace-nowrap">
                            {fmtDateShort(paidAt)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* ── Cart Items (Pending Payment) ───────────────────────────────── */}
          <section>
            <h2 className="text-lg font-semibold mb-3">
              Cart — Pending Payment
              {cartItems.length > 0 && (
                <span className="ml-2 text-sm font-normal text-gray-400">({cartItems.length})</span>
              )}
            </h2>
            {cartItems.length === 0 ? (
              <p className="text-gray-500 text-sm">No items awaiting payment.</p>
            ) : (
              <>
                <div className="overflow-x-auto rounded-lg border border-gray-800">
                  <table className="mat-table text-left">
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th className="text-right">Winning Bid</th>
                        <th className="text-right">Retail</th>
                        <th>Reserved Until</th>
                        <th>Condition</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {cartItems.map((item, idx) => {
                        const auctionId = item.auctionId || item.auction_id || item.id
                        const title     = item.item?.title || item.title || item.itemTitle || item.handle || item.name || '?'
                        const price     = item.winningBid?.amount ?? item.price ?? item.finalPrice ?? item.amount
                        const retail    = item.retailPrice || item.retail || item.estimatedRetail
                        const condition = item.condition || '—'
                        const reservedUntil = item.expiresAt || item.endDate || item.reservedUntil
                        return (
                          <tr key={auctionId || idx}>
                            <td className="max-w-md truncate">{title}</td>
                            <td className="text-right text-bw-green font-mono">
                              {price != null ? `$${Number(price).toFixed(2)}` : '—'}
                            </td>
                            <td className="text-right font-mono">
                              {retail != null ? `$${Number(retail).toFixed(2)}` : '—'}
                            </td>
                            <td className="whitespace-nowrap text-xs">
                              {reservedUntil ? fmtDate(reservedUntil) : '—'}
                            </td>
                            <td>{condition}</td>
                            <td>
                              <button
                                onClick={() => handleRemoveItem(auctionId, title)}
                                className="btn btn-danger text-xs"
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Checkout */}
                <div className="mt-4 space-y-2">
                  <div className="flex items-center gap-4 flex-wrap">
                    {payMethods.length > 0 && (
                      <p className="text-sm text-gray-400">
                        Pay with {payMethods[0]?.cardType || payMethods[0]?.brand || 'Card'} ending{' '}
                        {payMethods[0]?.last4 || '****'}
                      </p>
                    )}
                    <button
                      onClick={handlePay}
                      disabled={paying}
                      className="btn bg-bw-green text-white hover:bg-bw-green/85 px-6"
                    >
                      {paying ? 'Processing…' : 'Pay & Checkout'}
                    </button>
                  </div>
                </div>
              </>
            )}
          </section>

          {/* ── Pickup Appointment ────────────────────────────────────────── */}
          <section>
            <h2 className="text-lg font-semibold mb-3">Pickup Appointment</h2>

            {activeVisit ? (
              <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-bw-green">
                      {activeVisit.status || 'Booked'}
                    </p>
                    <p className="text-sm text-white mt-0.5">
                      {fmtDate(activeVisit.date)}
                    </p>
                    {(activeVisit.items || activeVisit.Items || []).length > 0 && (
                      <p className="text-xs text-gray-400 mt-1">
                        {(activeVisit.items || activeVisit.Items).length} item(s) scheduled for pickup
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => handleCancelAppointment(
                      activeVisit.id,
                      activeVisit.date,
                    )}
                    disabled={cancellingAppt}
                    className="btn btn-danger text-xs whitespace-nowrap"
                  >
                    {cancellingAppt ? 'Cancelling…' : 'Cancel Appointment'}
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-sm mb-3">No pickup appointment scheduled.</p>
            )}

            {/* Schedule button / form */}
            {!scheduleOpen ? (
              <button
                onClick={() => {
                  setScheduleOpen(true)
                  setAvailSlots([])
                  setSlotsError('')
                  setScheduleDay(todayStr())
                }}
                className="btn btn-secondary mt-3"
              >
                {activeVisit ? 'Reschedule Pickup' : 'Schedule Pickup'}
              </button>
            ) : (
              <div className="mt-3 bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-4">
                <h3 className="text-sm font-medium">Schedule Pickup Appointment</h3>

                {/* Day picker */}
                <div className="flex items-end gap-3">
                  <div>
                    <label htmlFor="schedule-day" className="block text-xs text-gray-400 mb-1">Select day</label>
                    <input
                      id="schedule-day"
                      type="date"
                      value={scheduleDay}
                      min={todayStr()}
                      disabled={slotsLoading}
                      onChange={e => {
                        setScheduleDay(e.target.value)
                        setAvailSlots([])
                        setSlotsError('')
                      }}
                      className="field"
                    />
                  </div>
                  <button
                    onClick={handleFetchSlots}
                    disabled={slotsLoading || !scheduleDay}
                    className="btn btn-primary"
                  >
                    {slotsLoading ? 'Loading…' : 'Find Slots'}
                  </button>
                  <button
                    onClick={() => { setScheduleOpen(false); setAvailSlots([]); setSlotsError('') }}
                    className="btn btn-secondary"
                  >
                    Cancel
                  </button>
                </div>

                {slotsError && <p className="text-bw-red text-xs">{slotsError}</p>}

                {/* Available slots */}
                {availSlots.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-400 mb-2">
                      Select a time slot:
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                      {availSlots.map((slot, idx) => {
                        const slotDate = typeof slot === 'string' ? slot : (slot.date || slot.visitDate)
                        const timeStr = slotDate
                          ? new Date(slotDate).toLocaleTimeString(undefined, {
                              hour: '2-digit', minute: '2-digit',
                            })
                          : '?'
                        return (
                          <button
                            key={idx}
                            onClick={() => handleSchedule(slotDate)}
                            disabled={scheduling}
                            className="py-2 px-3 bg-gray-700 hover:bg-bw-blue/70 border border-gray-600 hover:border-bw-blue rounded text-sm text-center transition-colors disabled:opacity-50"
                          >
                            {timeStr}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
