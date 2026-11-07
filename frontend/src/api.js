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

// --- Upload flow (Person A) -------------------------------------------------------------
// Unlike request(), this keeps the backend's { code, message, next_step } on the thrown error
// so pages can show a plain message and a next step.
async function requestWithDetail(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let detail = {}
    try {
      detail = (await res.json()).detail ?? {}
    } catch {
      // non-JSON error body; fall through to the generic message
    }
    const err = new Error(detail.message ?? `Request failed (${res.status})`)
    err.code = detail.code
    err.nextStep = detail.next_step
    err.status = res.status
    throw err
  }
  return res.json()
}

// file: File from <input type="file">. lat/lon: from browser geolocation (confirmed by the user).
// takenAt: optional ISO string, used only if the photo's EXIF has no time.
// Returns { job_id }.
export function uploadMeasurement(file, { lat, lon, takenAt } = {}) {
  const form = new FormData()
  form.append('image', file)
  form.append('lat', String(lat))
  form.append('lon', String(lon))
  if (takenAt) form.append('taken_at', takenAt)
  // Minutes EAST of UTC (US Eastern in winter = -300); EXIF times often lack a time zone.
  form.append('tz_offset_minutes', String(-new Date().getTimezoneOffset()))
  return requestWithDetail('/api/measurements', { method: 'POST', body: form })
}

// Returns { job_id, status: 'pending'|'solved'|'failed', step, result, error, image_url,
// taken_at_utc, lat, lon, flags }. image_url may be relative: prefix it with the API base in prod.
export const getMeasurement = (jobId) => requestWithDetail(`/api/measurements/${jobId}`)
