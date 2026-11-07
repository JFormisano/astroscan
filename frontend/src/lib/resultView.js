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
    planets: Array.isArray(r.planets) ? r.planets : [],
    sources: Array.isArray(r.sources) ? r.sources : [],
    warnings: Array.isArray(r.warnings) ? r.warnings : [],
    score: r.score && typeof r.score.value === 'number' ? r.score : null,
    stats: hasStats ? stats : null,
    explainer: typeof r.explainer === 'string' ? r.explainer : null,
    // True once Person B's matching has run (catalog stars projected into the photo).
    analyzed: stars.length > 0,
  }
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
