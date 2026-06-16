import { describe, expect, it } from 'vitest'
import { appendUniqueAuctions, uniqueAuctions } from './Browse'

describe('Browse auction merging', () => {
  it('deduplicates auctions within a page by stable identity', () => {
    const first = { id: 'auction-1', item: { title: 'First copy' } }
    const duplicate = { id: 'auction-1', item: { title: 'Second copy' } }
    const unique = { handle: 'auction-2', item: { title: 'Different auction' } }

    expect(uniqueAuctions([first, duplicate, unique])).toEqual([first, unique])
  })

  it('appends only new auctions when later pages overlap earlier pages', () => {
    const current = [
      { id: 'auction-1', item: { title: 'Already loaded' } },
      { handle: 'auction-2', item: { title: 'Also loaded' } },
    ]
    const incoming = [
      { id: 'auction-1', item: { title: 'Repeated by upstream page' } },
      { handle: 'auction-2', item: { title: 'Repeated by handle' } },
      { id: 'auction-3', item: { title: 'New result' } },
    ]

    expect(appendUniqueAuctions(current, incoming)).toEqual([
      ...current,
      incoming[2],
    ])
  })
})
