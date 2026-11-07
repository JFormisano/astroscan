// Person C (#5). Picks which stars get a label so a real photo isn't buried in text.
// Display-only: positions and names come from Person B's matching; nothing is computed here
// except screen spacing in image pixels.
//
// Matching sends name = proper name or catalog designation ("Dubhe", "52Psi UMa", "29    Psc").
// A real 60° field has ~60 named detected stars, so we label:
//   1. proper names, brightest first, up to MAX_LABELS, skipping any too close to one already placed
//   2. if that gives fewer than MIN_LABELS, Greek-letter designations shown as "ψ UMa"
// Bare Flamsteed numbers ("29 Psc") are never labeled.

const MAX_LABELS = 12
const MIN_LABELS = 5
const SPACING = 0.07 // minimum gap between label anchors, as a fraction of the image's long side

const GREEK = {
  Alp: 'α', Bet: 'β', Gam: 'γ', Del: 'δ', Eps: 'ε', Zet: 'ζ', Eta: 'η', The: 'θ',
  Iot: 'ι', Kap: 'κ', Lam: 'λ', Mu: 'μ', Nu: 'ν', Xi: 'ξ', Omi: 'ο', Pi: 'π',
  Rho: 'ρ', Sig: 'σ', Tau: 'τ', Ups: 'υ', Phi: 'φ', Chi: 'χ', Psi: 'ψ', Ome: 'ω',
}
const SUPERSCRIPT = { 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' }

// "52Psi UMa", "Alp1 Cen", "Tau Phe", "29    Psc" → { flamsteed, greek, index, con }; else null.
const DESIGNATION = /^(\d+)?\s*([A-Z][a-z]{1,2})?(\d)?\s+([A-Z][A-Za-z]{2})$/

export function parseDesignation(name) {
  const m = DESIGNATION.exec(name.trim())
  if (!m) return null
  const [, flamsteed, greek, index, con] = m
  if (greek && !GREEK[greek]) return null // e.g. "Cor Car" is not a designation
  if (!flamsteed && !greek) return null
  return { flamsteed, greek, index, con }
}

// Returns { proper, greek } display strings for one star (either may be null).
export function displayNames(star) {
  const raw = (star.name ?? '').trim()
  // If matching later sends the proper name separately, trust it.
  if (star.proper) return { proper: star.proper.trim(), greek: greekLabel(star.bayer_flamsteed) }
  if (!raw) return { proper: null, greek: null }
  return parseDesignation(raw) ? { proper: null, greek: greekLabel(raw) } : { proper: raw, greek: null }
}

function greekLabel(name) {
  const d = name ? parseDesignation(name) : null
  if (!d?.greek) return null
  return `${GREEK[d.greek]}${d.index ? SUPERSCRIPT[d.index] ?? d.index : ''} ${d.con}`
}

// stars: matching output; occupied: [{x, y}] already used (e.g. constellation labels).
export function pickStarLabels(stars, width, height, occupied = []) {
  const minGap = SPACING * Math.max(width, height)
  const placed = []
  const taken = [...occupied]
  const free = (s) => taken.every((p) => Math.hypot(p.x - s.x, p.y - s.y) >= minGap)
  const candidates = stars
    .filter((s) => s.detected && Number.isFinite(s.x) && Number.isFinite(s.y))
    .map((s) => ({ ...s, ...displayNames(s) }))
    .sort((a, b) => a.mag - b.mag)

  const place = (key, limit) => {
    for (const s of candidates) {
      if (placed.length >= limit) return
      if (!s[key] || placed.some((p) => p.id === s.id) || !free(s)) continue
      placed.push({ id: s.id, x: s.x, y: s.y, text: s[key] })
      taken.push(s)
    }
  }
  place('proper', MAX_LABELS)
  if (placed.length < MIN_LABELS) place('greek', MIN_LABELS)
  return placed
}
