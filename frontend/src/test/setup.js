import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

function createMemoryStorage() {
  const store = new Map()
  return {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key) {
      return store.has(key) ? store.get(key) : null
    },
    key(index) {
      return Array.from(store.keys())[index] ?? null
    },
    removeItem(key) {
      store.delete(key)
    },
    setItem(key, value) {
      store.set(String(key), String(value))
    },
  }
}

if (!globalThis.localStorage) {
  const memoryStorage = createMemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', {
    value: memoryStorage,
    configurable: true,
  })
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', {
      value: memoryStorage,
      configurable: true,
    })
  }
}

window.history.replaceState({}, '', 'http://localhost:3000/')

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.clearAllMocks()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
