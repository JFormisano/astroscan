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
