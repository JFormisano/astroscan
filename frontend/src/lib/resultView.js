// Person C. Turns a job response into what the results screens draw, whatever stage it's at:
//   - demo / agreed shape: result has image, stars, score, ... (demo_cache/, src/fake/)
//   - raw solver block today: result is { solver_used, wcs, sources, stats } (docs/solver-output.md)
//   - stub solver: result is { stub: true, ... }
// The image may sit in result.image or at the top level (image_url + flags.image_w/h).
// Nothing here does astronomy math; it only picks fields and fills gaps with empties.
import { apiUrl } from '../api.js'

export function toView(job) {
  const r = job?.result ?? {}
  const flags = job?.flags ?? {}
  const width = r.image?.width ?? r.stats?.image_width_px ?? flags.image_w
  const height = r.image?.height ?? r.stats?.image_height_px ?? flags.image_h
  const imageUrl = apiUrl(r.image?.url ?? job?.image_url ?? null)

  const stats = { ...(r.stats ?? {}) }
  stats.solver_used ??= r.solver_used ?? flags.solver_used
  stats.solve_seconds ??= flags.solve_seconds
  const hasStats = Object.values(stats).some((v) => v != null)

  const stars = Array.isArray(r.stars) ? r.stars : []
  return {
    // Without a pixel size we can't place overlays; the view falls back to a plain <img>.
    image: width && height ? { url: imageUrl, width, height } : null,
    imageUrl,
    stars,
    constellations: Array.isArray(r.constellations) ? r.constellations : [],
    // Only planets the backend placed on the photo (pixel x/y inside the frame).
    planets: (Array.isArray(r.planets) ? r.planets : []).filter(
      (p) => Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.y >= 0 &&
        (!width || p.x < width) && (!height || p.y < height) && p.above_horizon !== false,
    ),
    sources: Array.isArray(r.sources) ? r.sources : [],
    warnings: toWarnings(r),
    score: r.score && typeof r.score.value === 'number' ? r.score : null,
    // Scoring ran but couldn't give a number (scoring.py returns value: null when too few
    // catalog stars are in view), as opposed to scoring not having run at all.
    scoreFailed: Boolean(r.score) && typeof r.score.value !== 'number',
    stats: hasStats ? stats : null,
    explainer: typeof r.explainer === 'string' ? r.explainer : null,
    // True once Person B's matching has run (catalog stars projected into the photo).
    analyzed: stars.length > 0,
  }
}

// Warnings as the banner wants them: [{ type: twilight|moon|low_altitude, moon_illumination_pct? }].
// Accepts that list (proposed schema) or Person B's evaluate_conditions() output passed through
// as result.conditions ({ flags: { twilight, moon_up, low_altitude }, moon_illumination_pct }).
// Which one the result uses is still to be agreed; this only renames fields, no math.
function toWarnings(r) {
  if (Array.isArray(r.warnings)) return r.warnings
  const c = r.conditions
  if (!c?.flags) return []
  const out = []
  if (c.flags.twilight) out.push({ type: 'twilight' })
  if (c.flags.moon_up) out.push({ type: 'moon', moon_illumination_pct: c.moon_illumination_pct })
  if (c.flags.low_altitude) out.push({ type: 'low_altitude' })
  return out
}

// Failure details. Real jobs use the top-level error (CLAUDE.md §3 API table); the older
// fake/demo shape put reason + stars_detected in result.
export function toFailure(job) {
  const e = job?.error ?? {}
  const r = job?.result ?? {}
  return {
    code: e.code ?? r.reason ?? null,
    message: e.message ?? r.message ?? null,
    nextStep: e.next_step ?? null,
    detected: e.detected_stars ?? r.stars_detected ?? null,
  }
}
