/**
 * Shared image extraction helper — deduplicates images from auction item data.
 * Used by Browse, Dashboard, and History modals.
 */
export function getAllImgs(item) {
  if (!item) return []
  const seen = new Set()
  const out = []
  const add = u => { if (u && typeof u === 'string' && !seen.has(u)) { seen.add(u); out.push(u) } }
  for (const arr of [item.images, item.imageUrls, item.additionalImages, item.galleryImages, item.photos, item.mediaUrls]) {
    if (Array.isArray(arr)) arr.forEach(x => add(typeof x === 'string' ? x : x?.url || x?.imageUrl || x?.src))
  }
  add(item.imageUrl); add(item.image); add(item.primaryImage); add(item.thumbnailUrl); add(item.thumbnail)
  return out
}
