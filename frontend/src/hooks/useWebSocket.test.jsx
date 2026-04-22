import { render } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

let currentToken = 'initial-token'
const refreshTokenMock = vi.fn()
const getTokenMock = vi.fn(() => currentToken)

vi.mock('./useApi', () => ({
  getToken: () => getTokenMock(),
  refreshToken: () => refreshTokenMock(),
}))

import { useWebSocket } from './useWebSocket'

class FakeWebSocket {
  static instances = []
  static OPEN = 1

  constructor(url) {
    this.url = url
    this.readyState = 0
    this.send = vi.fn()
    this.close = vi.fn()
    FakeWebSocket.instances.push(this)
  }

  async open() {
    this.readyState = FakeWebSocket.OPEN
    await this.onopen?.()
  }

  async closeWith(code) {
    this.readyState = 3
    await this.onclose?.({ code })
  }
}

function Harness() {
  useWebSocket(vi.fn())
  return null
}

describe('useWebSocket auth recovery', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeWebSocket.instances = []
    currentToken = 'initial-token'
    getTokenMock.mockReset()
    getTokenMock.mockImplementation(() => currentToken)
    refreshTokenMock.mockReset()
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  it('refreshes the token after a 4001 auth close and reconnects immediately', async () => {
    currentToken = 'expired-token'
    refreshTokenMock.mockImplementation(async () => {
      currentToken = 'fresh-token'
      return currentToken
    })

    render(<Harness />)

    expect(FakeWebSocket.instances).toHaveLength(1)

    await act(async () => {
      await FakeWebSocket.instances[0].open()
    })
    expect(FakeWebSocket.instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'auth', token: 'expired-token' })
    )

    await act(async () => {
      await FakeWebSocket.instances[0].closeWith(4001)
      await Promise.resolve()
      vi.runOnlyPendingTimers()
    })

    expect(refreshTokenMock).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(2)

    await act(async () => {
      await FakeWebSocket.instances[1].open()
    })
    expect(FakeWebSocket.instances[1].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'auth', token: 'fresh-token' })
    )
  })

  it('does not reconnect with the stale token when refresh fails and auth is cleared', async () => {
    currentToken = 'expired-token'
    refreshTokenMock.mockImplementation(async () => {
      currentToken = null
      return null
    })

    render(<Harness />)

    await act(async () => {
      await FakeWebSocket.instances[0].open()
      await FakeWebSocket.instances[0].closeWith(4001)
      await Promise.resolve()
      vi.runOnlyPendingTimers()
    })

    expect(refreshTokenMock).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('waits for the standard reconnect delay on non-auth socket closes', async () => {
    currentToken = 'valid-token'
    refreshTokenMock.mockResolvedValue('unexpected-refresh')

    render(<Harness />)

    await act(async () => {
      await FakeWebSocket.instances[0].open()
      await FakeWebSocket.instances[0].closeWith(1006)
    })

    expect(refreshTokenMock).not.toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(1)

    await act(async () => {
      vi.advanceTimersByTime(2999)
    })
    expect(FakeWebSocket.instances).toHaveLength(1)

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(FakeWebSocket.instances).toHaveLength(2)
  })
})
