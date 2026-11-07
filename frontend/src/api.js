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
    throw err
  }
  return res.json()
}

// POST /api/measurements → { job_id }. takenAt is a Date; sent as UTC ISO 8601.
export async function createMeasurement(file, { lat, lon, takenAt }) {
  if (FAKE) return (await import('./fake/fakeApi.js')).createMeasurement(file)
  const body = new FormData()
  body.append('image', file)
  body.append('lat', String(lat))
  body.append('lon', String(lon))
  body.append('taken_at', takenAt.toISOString())
  return measurementRequest('/api/measurements', { method: 'POST', body })
}

// GET /api/measurements/{job_id} → { status: pending|solved|failed, step?, result? }
export async function getMeasurement(jobId) {
  if (FAKE) return (await import('./fake/fakeApi.js')).getMeasurement(jobId)
  return measurementRequest(`/api/measurements/${encodeURIComponent(jobId)}`)
}
