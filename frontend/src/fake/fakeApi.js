// DEV ONLY (Person C). Stands in for Person A's measurement routes when VITE_FAKE_API=1.
// Responses use the real envelope from CLAUDE.md §3 (top-level error, image_url, flags).
// The file name picks the outcome:
//   contains "fail" → failed with too_few_stars
//   contains "raw"  → solved, but only the raw solver block (before B's matching/scoring)
//   anything else   → solved with the full proposed result shape
import { fakeSolved } from './fakeResult.js'

const STEPS = ['queued', 'detecting', 'solving', 'matching', 'scoring']
const STEP_MS = 1200
const started = {}

export async function createMeasurement(file) {
  await new Promise((r) => setTimeout(r, 600))
  const kind = /fail/i.test(file.name) ? 'failed' : /raw/i.test(file.name) ? 'raw' : 'full'
  const jobId = `fake-${kind}-${Date.now()}`
  started[jobId] = Date.now()
  return { job_id: jobId }
}

const envelope = (jobId, fields) => ({
  job_id: jobId,
  step: null,
  result: null,
  error: null,
  image_url: null,
  taken_at_utc: fakeSolved.taken_at_utc,
  lat: 43.0,
  lon: -78.79,
  flags: { image_w: fakeSolved.image.width, image_h: fakeSolved.image.height, solve_seconds: 14.2, solver_used: 'local' },
  ...fields,
})

// Same field names as docs/solver-output.md; sources come from the full fake.
const rawSolverBlock = {
  solver_used: 'local',
  wcs: { CTYPE1: 'RA---TAN-SIP', CTYPE2: 'DEC--TAN-SIP' },
  sources: fakeSolved.sources.map((s) => ({ ...s, flux: 1000 })),
  stats: {
    image_width_px: fakeSolved.image.width,
    image_height_px: fakeSolved.image.height,
    stars_detected: fakeSolved.sources.length,
    stars_matched: 41,
    log_odds: 210.4,
    field_width_deg: 38.2,
    field_height_deg: 28.9,
    solve_seconds: 14.2,
  },
}

export async function getMeasurement(jobId) {
  if (!jobId.startsWith('fake-')) {
    const err = new Error('Not found')
    err.status = 404
    err.code = 'job_not_found'
    err.userMessage = "We couldn't find that result."
    throw err
  }
  // After a refresh the start time is gone; treat the job as finished.
  const elapsed = Date.now() - (started[jobId] ?? 0)
  const i = Math.floor(elapsed / STEP_MS)
  const kind = jobId.split('-')[1]
  if (i < (kind === 'full' ? STEPS.length : 3)) return envelope(jobId, { status: 'pending', step: STEPS[i] })
  if (kind === 'failed') {
    return envelope(jobId, {
      status: 'failed',
      error: {
        code: 'too_few_stars',
        message: 'Too few stars to identify.',
        next_step:
          "Very few visible stars is itself a sign of heavy light pollution (or cloud). Take the photo with your phone's Night mode, away from bright lights, holding it steady, then upload it again.",
        detected_stars: 4,
      },
    })
  }
  if (kind === 'raw') return envelope(jobId, { status: 'solved', result: rawSolverBlock })
  return envelope(jobId, { status: 'solved', result: fakeSolved })
}
