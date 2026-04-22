import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

window.history.replaceState({}, '', 'http://localhost:3000/')

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.clearAllMocks()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
