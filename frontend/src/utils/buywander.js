const BUY_WANDER_AUCTIONS_URL = 'https://www.buywander.com/auctions'
const LEGACY_UUID_AUCTION_PATH = /^\/auction\/([0-9a-f-]+)\/?$/i

function legacyAuctionId(url) {
  try {
    const parsed = new URL(url)
    return ['buywander.com', 'www.buywander.com'].includes(parsed.hostname)
      ? parsed.pathname.match(LEGACY_UUID_AUCTION_PATH)?.[1] || ''
      : ''
  } catch {
    return ''
  }
}

export function buyWanderAuctionUrl(auction) {
  const nested = auction?.auction || auction?.data || auction
  const id = auction?.auction_uuid || auction?.auction_id || nested?.id
  if (id) return `${BUY_WANDER_AUCTIONS_URL}?auctionId=${encodeURIComponent(id)}`

  const url = typeof auction?.url === 'string' ? auction.url.trim() : ''
  const legacyId = legacyAuctionId(url)
  if (url && !legacyId && !/^https?:\/\/(?:www\.)?buywander\.com\/auctions\/?$/.test(url)) return url

  return legacyId ? `${BUY_WANDER_AUCTIONS_URL}?auctionId=${encodeURIComponent(legacyId)}` : ''
}
