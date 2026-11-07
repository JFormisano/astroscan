// DEV ONLY (Person C). A hand-made result so the results page can be built before real
// solves work. Enable with VITE_FAKE_API=1 in frontend/.env.local.
//
// This is a PROPOSED shape for /docs/result-schema.json, not the agreed one. The team agrees
// on the schema together (CLAUDE.md §2); update this file to match whatever is decided.
//
// Proposed shape (all overlay coordinates in image pixels, origin top-left, x right, y down):
// GET /api/measurements/{job_id} →
// {
//   job_id, status: "pending" | "solved" | "failed",
//   step?: "queued" | "detecting" | "solving" | "matching" | "scoring",   // while pending
//   result?: {
//     image: { url, width, height },            // EXIF-stripped copy
//     taken_at_utc, location: { lat, lon },     // rounded
//     score: { value 1–9, limiting_mag, pct_lost 0–100, confidence: high|medium|low },
//     stars: [{ id, name|null, x, y, mag, detected }],   // detected=false → ghost star
//     constellations: [{ name, label: {x, y}, lines: [[x1, y1, x2, y2], ...] }],
//     planets: [{ name, x, y, mag }],
//     warnings: [{ type: "twilight"|"moon"|"low_altitude", moon_illumination_pct?, message? }],
//     sources: [{ x, y }],                      // what the solver detected (under the hood)
//     stats: { stars_detected, stars_matched, catalog_in_frame, field_width_deg,
//              field_height_deg, solve_seconds, solver_used },
//     explainer: string | null,                 // AI text (Person D), optional
//   }
// }
// Failed: { status: "failed", result: { reason: "too_few_stars"|"no_match"|"timeout",
//           stars_detected, message? } }

const W = 1600
const H = 1200

// Deterministic pseudo-random numbers so the fake looks the same on every reload.
function rng(seed) {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296
    return s / 4294967296
  }
}

const orion = [
  { id: 'betelgeuse', name: 'Betelgeuse', x: 640, y: 330, mag: 0.5 },
  { id: 'bellatrix', name: 'Bellatrix', x: 930, y: 370, mag: 1.6 },
  { id: 'mintaka', name: 'Mintaka', x: 860, y: 600, mag: 2.2 },
  { id: 'alnilam', name: 'Alnilam', x: 800, y: 630, mag: 1.7 },
  { id: 'alnitak', name: 'Alnitak', x: 740, y: 665, mag: 1.8 },
  { id: 'saiph', name: 'Saiph', x: 690, y: 930, mag: 2.1 },
  { id: 'rigel', name: 'Rigel', x: 990, y: 900, mag: 0.1 },
  { id: 'meissa', name: 'Meissa', x: 790, y: 230, mag: 3.4 },
]

function makeStars() {
  const rand = rng(42)
  const stars = orion.map((s) => ({ ...s, detected: s.mag < 3 }))
  for (let i = 0; i < 260; i++) {
    const mag = 3 + rand() * 4 // 3.0–7.0
    stars.push({
      id: `hyg-${i}`,
      name: null,
      x: Math.round(rand() * W),
      y: Math.round(rand() * H),
      mag: Math.round(mag * 10) / 10,
      // Bright ones mostly detected, faint ones mostly lost: limiting mag ≈ 4.3
      detected: rand() < 1 / (1 + Math.exp((mag - 4.3) * 3)),
    })
  }
  return stars
}

function makeResult() {
  const stars = makeStars()
  const rand = rng(7)
  const p = Object.fromEntries(orion.map((s) => [s.id, [s.x, s.y]]))
  const seg = (a, b) => [...p[a], ...p[b]]
  const detected = stars.filter((s) => s.detected)
  const sources = detected.map((s) => ({ x: s.x + (rand() - 0.5) * 4, y: s.y + (rand() - 0.5) * 4 }))
  for (let i = 0; i < 12; i++) sources.push({ x: rand() * W, y: rand() * H }) // noise / hot pixels

  return {
    image: { url: null, width: W, height: H },
    taken_at_utc: '2026-11-07T03:12:00Z',
    location: { lat: 43.0, lon: -78.79 },
    score: { value: 7, limiting_mag: 4.3, pct_lost: 78, confidence: 'medium' },
    stars,
    constellations: [
      {
        name: 'Orion',
        label: { x: 1010, y: 520 },
        lines: [
          seg('betelgeuse', 'bellatrix'),
          seg('betelgeuse', 'alnitak'),
          seg('bellatrix', 'mintaka'),
          seg('mintaka', 'alnilam'),
          seg('alnilam', 'alnitak'),
          seg('alnitak', 'saiph'),
          seg('mintaka', 'rigel'),
          seg('betelgeuse', 'meissa'),
          seg('bellatrix', 'meissa'),
        ],
      },
    ],
    planets: [{ name: 'Jupiter', x: 300, y: 180, mag: -2.6 }],
    warnings: [{ type: 'moon', moon_illumination_pct: 42 }],
    sources,
    stats: {
      stars_detected: sources.length,
      stars_matched: detected.length,
      catalog_in_frame: stars.length,
      field_width_deg: 38.2,
      field_height_deg: 28.9,
      solve_seconds: 14.2,
      solver_used: 'local',
    },
    explainer: null,
  }
}

export const fakeSolved = makeResult()

export const fakeFailed = {
  reason: 'too_few_stars',
  stars_detected: 4,
}
