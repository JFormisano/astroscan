// All backend calls live here. Add your own functions; don't change anyone else's.
// In dev, Vite proxies /api to the backend (see vite.config.js).
// In production, set VITE_API_URL to the deployed backend origin.
const BASE = import.meta.env.VITE_API_URL ?? ''

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.json()
}

export const getHealth = () => request('/api/health')

// ---- Person C: measurements (upload + polling) ----------------------------------------
// Set VITE_FAKE_API=1 in .env.local to use the dev-only fake backend in src/fake/.
const FAKE = import.meta.env.VITE_FAKE_API === '1'

// Errors carry .status (HTTP code, or 0 for network failure) so pages can pick a message.
// When the backend sends {"detail": {code, message, next_step}} (app/errors.py), they also
// carry .code, .userMessage and .nextStep, which pages show as-is.
async function measurementRequest(path, options) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, options)
  } catch {
    const err = new Error('Network error')
    err.status = 0
    throw err
  }
  if (!res.ok) {
    const err = new Error(`Request failed (${res.status})`)
    err.status = res.status
    try {
      const detail = (await res.json())?.detail
      if (detail && typeof detail === 'object') {
        err.code = detail.code
        err.userMessage = detail.message
        err.nextStep = detail.next_step
      }
    } catch {
      // Not JSON (e.g. a proxy error page): status alone will do.
    }
    throw err
  }
  return res.json()
}

// Turns a backend-relative path (LocalStore serves /api/measurements/{id}/image) into a URL
// the browser can load in production too. Absolute URLs (Supabase storage) pass through.
export const apiUrl = (path) => (path && path.startsWith('/') ? `${BASE}${path}` : path)

// POST /api/measurements → { job_id }. takenAt is a Date; sent as UTC ISO 8601.
// The backend prefers the EXIF time; taken_at + tz_offset_minutes are its fallback.
export async function createMeasurement(file, { lat, lon, takenAt }) {
  if (FAKE) return (await import('./fake/fakeApi.js')).createMeasurement(file)
  const body = new FormData()
  body.append('image', file)
  body.append('lat', String(lat))
  body.append('lon', String(lon))
  body.append('taken_at', takenAt.toISOString())
  // Minutes EAST of UTC at the photo's time (so DST is right for that date).
  body.append('tz_offset_minutes', String(-takenAt.getTimezoneOffset()))
  return measurementRequest('/api/measurements', { method: 'POST', body })
}

// GET /api/measurements/{job_id} → { job_id, status, step, result, error, image_url, flags, ... }
// See the API table in CLAUDE.md §3. Pages normalize it with lib/resultView.js.
export async function getMeasurement(jobId) {
  if (FAKE) return (await import('./fake/fakeApi.js')).getMeasurement(jobId)
  return measurementRequest(`/api/measurements/${encodeURIComponent(jobId)}`)
}

// ---- Person D: map (#8) ----------------------------------------------------------------
// GET /api/map → { measurements: [...], light_reports: [...] }
export const getMap = () => request('/api/map')

// ---- Person D: demo mode (#11) ---------------------------------------------------------
// GET /api/demo/{name} → a cached result, same shape as getMeasurement(). Errors carry .status.
export const getDemo = (name) => measurementRequest(`/api/demo/${encodeURIComponent(name)}`)

// ---- Person D: light reports (#9) ------------------------------------------------------
// POST /api/light-reports → the saved report incl. drafted_message and draft_source ("ai" | "template").
// Errors carry .status (0 = network) and .detail ({ code, message, next_step }) when the backend sent one.
export async function createLightReport({ lat, lon, category, controller, note, photo }) {
  const body = new FormData()
  body.append('lat', String(lat))
  body.append('lon', String(lon))
  body.append('category', category)
  body.append('controller', controller)
  if (note) body.append('note', note)
  if (photo) body.append('photo', photo)

  let res
  try {
    res = await fetch(`${BASE}/api/light-reports`, { method: 'POST', body })
  } catch {
    const err = new Error('Network error')
    err.status = 0
    throw err
  }
  if (!res.ok) {
    const err = new Error(`Request failed (${res.status})`)
    err.status = res.status
    try {
      const detail = (await res.json()).detail
      if (detail && typeof detail === 'object' && detail.message) err.detail = detail
    } catch {
      // not JSON: keep the generic error
    }
    throw err
  }
  return res.json()
}
