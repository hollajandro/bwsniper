import { describe, expect, it } from 'vitest'
import { buyWanderAuctionUrl } from './buywander'

describe('buyWanderAuctionUrl', () => {
  it('keeps a canonical URL supplied by BuyWander', () => {
    const url = 'https://www.buywander.com/auctions/canonical-handle'

    expect(buyWanderAuctionUrl({ url, item: { handle: 'other-handle' } })).toBe(url)
  })

  it('prefers UUID links over retired handle routes', () => {
    expect(buyWanderAuctionUrl({ id: 'auction-1', url: 'https://www.buywander.com/auctions/old-handle', item: { handle: 'old-handle' } })).toBe(
      'https://www.buywander.com/auctions?auctionId=auction-1',
    )
  })

  it('uses a nested detail UUID when the top-level response has no URL', () => {
    expect(buyWanderAuctionUrl({ auction: { id: 'auction-1' } })).toBe(
      'https://www.buywander.com/auctions?auctionId=auction-1',
    )
  })

  it('replaces the old UUID path even if a handle remains cached', () => {
    expect(buyWanderAuctionUrl({
      url: 'https://www.buywander.com/auction/550e8400-e29b-41d4-a716-446655440000',
      item: { handle: 'correct-handle' },
    })).toBe('https://www.buywander.com/auctions?auctionId=550e8400-e29b-41d4-a716-446655440000')
  })

  it('uses the current UUID deep link when a handle is missing', () => {
    const id = '550e8400-e29b-41d4-a716-446655440000'
    expect(buyWanderAuctionUrl({ id, item: { handle: null } })).toBe(
      `https://www.buywander.com/auctions?auctionId=${id}`,
    )
  })

  it('repairs a stored singular UUID link even without auction details', () => {
    const id = '550e8400-e29b-41d4-a716-446655440000'
    expect(buyWanderAuctionUrl({ url: `https://www.buywander.com/auction/${id}` })).toBe(
      `https://www.buywander.com/auctions?auctionId=${id}`,
    )
  })

  it('repairs history links with an empty handle', () => {
    expect(buyWanderAuctionUrl({ url: 'https://www.buywander.com/auctions/', auction_id: 'auction-1' })).toBe(
      'https://www.buywander.com/auctions?auctionId=auction-1',
    )
  })

  it('returns no link when the auction has no URL or identity', () => {
    expect(buyWanderAuctionUrl({})).toBe('')
  })

  it('uses the auction UUID instead of a local snipe or history record ID', () => {
    expect(buyWanderAuctionUrl({ id: 'snipe-1', auction_uuid: 'auction-1' })).toBe(
      'https://www.buywander.com/auctions?auctionId=auction-1',
    )
    expect(buyWanderAuctionUrl({ id: 'history-1', auction_id: 'auction-1' })).toBe(
      'https://www.buywander.com/auctions?auctionId=auction-1',
    )
  })
})
