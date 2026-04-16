/**
 * useWebSocket — manages a WebSocket connection with first-message JWT auth.
 *
 * Protocol (matches backend api/websocket.py):
 *   1. Connect to /ws  (no token in URL — avoids server log exposure)
 *   2. On open: immediately send {"type":"auth","token":"<access_token>"}
 *   3. Server replies {"type":"auth_ok"}
 *   4. Normal message loop: {"type":"ping"} / {"type":"pong"}, event push
 *   5. Auto-reconnect every 3 s on close.
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import { getToken } from './useApi'

const RECONNECT_DELAY = 3000
const PING_INTERVAL   = 30_000

export function useWebSocket(onMessage) {
  const wsRef           = useRef(null)
  const pingTimerRef    = useRef(null)
  const reconnectTimer  = useRef(null)
  const mountedRef      = useRef(true)
  const onMessageRef    = useRef(onMessage)
  const [connected, setConnected] = useState(false)

  // Keep the ref current without triggering reconnects
  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])

  const clearTimers = () => {
    clearInterval(pingTimerRef.current)
    clearTimeout(reconnectTimer.current)
  }

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    const token = getToken()
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws`)

    ws.onopen = () => {
      // Step 2: send auth as the very first message
      ws.send(JSON.stringify({ type: 'auth', token }))

      // Heartbeat so nginx / load-balancers don't idle-close us
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        }
      }, PING_INTERVAL)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // auth_ok / pong are infrastructure; don't forward to consumer
        if (data.type === 'auth_ok') {
          setConnected(true)
          return
        }
        if (data.type === 'pong') return
        onMessageRef.current?.(data)
      } catch { /* ignore non-JSON */ }
    }

    ws.onclose = () => {
      clearTimers()
      setConnected(false)
      wsRef.current = null
      if (mountedRef.current) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY)
      }
    }

    ws.onerror = () => ws.close()

    wsRef.current = ws
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimers()
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { connected, send }
}
