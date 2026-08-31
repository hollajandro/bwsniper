import { describe, expect, it } from 'vitest'
import {
  appendUniqueAuctions,
  auctionIdentityKeys,
  auctionMatchesKeys,
  auctionSearchCursor,
  endsOnLocalDay,
  hasMoreAuctionResults,
  recentAuctionSummary,
  serverAuctionFilter,
  uniqueAuctions,
} from './Browse'

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

describe('Browse cursor pagination', () => {
  it('uses the v1 hasNextPage flag instead of inferred page numbers', () => {
    expect(hasMoreAuctionResults({ hasNextPage: true, totalPages: 1 }, 1)).toBe(true)
    expect(hasMoreAuctionResults({ hasNextPage: false, totalPages: 20 }, 1)).toBe(false)
  })

  it('falls back to totalPages for legacy responses', () => {
    expect(hasMoreAuctionResults({ totalPages: 3 }, 1)).toBe(true)
    expect(hasMoreAuctionResults({ totalPages: 3 }, 3)).toBe(false)
  })

  it('extracts the cursor needed for the next v1 search request', () => {
    const data = {
      nextSearchAfter: [1788220800000, 'auction-24'],
      searchId: 'search-session-1',
    }

    expect(auctionSearchCursor(data)).toEqual({
      searchAfter: data.nextSearchAfter,
      searchId: 'search-session-1',
    })
  })
})

describe('Browse quick filters', () => {
  it('matches nested v1 item handles as well as auction UUIDs', () => {
    const auction = { id: 'auction-1', item: { handle: 'nested-handle' } }

    expect(auctionIdentityKeys(auction)).toContain('nested-handle')
    expect(auctionMatchesKeys(auction, new Set(['nested-handle']))).toBe(true)
  })

  it('selects a supported server filter with date filters first', () => {
    expect(serverAuctionFilter(['NoBidsYet', 'EndsTomorrow'])).toBe('EndsTomorrow')
    expect(serverAuctionFilter(['Sniped', 'Watched'])).toBeNull()
  })

  it('treats tomorrow as the next local calendar day', () => {
    const now = new Date(2026, 7, 31, 23, 30).getTime()
    const tomorrow = { endDate: new Date(2026, 8, 1, 0, 15).toISOString() }
    const laterToday = { endDate: new Date(2026, 7, 31, 23, 45).toISOString() }

    expect(endsOnLocalDay(tomorrow, 1, now)).toBe(true)
    expect(endsOnLocalDay(laterToday, 1, now)).toBe(false)
  })
})

describe('Browse recent auction summaries', () => {
  it('preserves the first v1 image-array URL', () => {
    const summary = recentAuctionSummary({
      id: 'auction-1',
      item: {
        title: 'Auction with image',
        images: ['https://example.com/image.jpg'],
      },
    })

    expect(summary.item.imageUrl).toBe('https://example.com/image.jpg')
  })
})
