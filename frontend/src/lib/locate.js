// Where the photo was taken, found on the phone before anything is uploaded.
// A device fix is rounded to ~1 km here, so a precise position never sits in the page.
// If the browser never answers (a common timeout on laptops), a network lookup
// fills in a coarser, city-level guess the user can correct.

const NETWORK_URLS = [
  'https://get.geojs.io/v1/ip/geo.json',
  'https://ipwho.is/',
]

// ~1.1 km in latitude. Longitude is a bit less except near the poles.
export function roundToKm(lat, lon) {
  const latN = Number(lat)
  const lonN = Number(lon)
  if (!Number.isFinite(latN) || !Number.isFinite(lonN)) return null
  if (latN < -90 || latN > 90 || lonN < -180 || lonN > 180) return null
  return {
    lat: Math.round(latN * 100) / 100,
    lon: Math.round(lonN * 100) / 100,
  }
}

export async function lookupNetworkLocation(fetchImpl = globalThis.fetch) {
  for (const url of NETWORK_URLS) {
    try {
      const res = await fetchImpl(url, {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(6000),
      })
      if (!res.ok) continue
      const data = await res.json()
      if (data?.success === false) continue
      const fix = roundToKm(data?.latitude, data?.longitude)
      if (!fix) continue
      const place = [data?.city, data?.region]
        .map((part) => (typeof part === 'string' ? part.trim() : ''))
        .filter(Boolean)
        .join(', ')
      return place ? { ...fix, place } : fix
    } catch {
      // That service failed; try the next one.
    }
  }
  return null
}

// Calls onFix({ lat, lon, source }) with source 'device' or 'network'.
// onFail receives a GeolocationPositionError code (1 blocked, 2 unavailable, 3 timeout).
// Returns a cancel function.
export function requestLocation({
  onFix,
  onFail,
  networkLookup = lookupNetworkLocation,
  networkDelayMs = 4000,
  giveUpMs = 20000,
  nav = globalThis.navigator,
} = {}) {
  let cancelled = false
  let sawDevice = false
  let sawAny = false
  let settledFail = false
  const watchIds = []
  const timers = []
  const geo = nav?.geolocation

  function clearTimers() {
    for (const timer of timers.splice(0)) clearTimeout(timer)
  }

  function clearWatches() {
    if (!geo) return
    for (const id of watchIds.splice(0)) {
      try {
        geo.clearWatch(id)
      } catch {
        // Already cleared.
      }
    }
  }

  function fail(code) {
    if (cancelled || sawAny || settledFail) return
    settledFail = true
    clearWatches()
    clearTimers()
    onFail?.(code)
  }

  function deliver(fix, source, accuracy) {
    if (cancelled || settledFail) return
    if (source !== 'device' && sawDevice) return
    if (source === 'device') {
      sawDevice = true
      // Accuracy is meters. Within 1.5 km is enough: we only keep two decimals.
      // A coarser first reading (cell tower) stays up so Wi-Fi or GPS can replace it.
      if (!(accuracy > 1500)) {
        clearWatches()
        clearTimers()
      }
    }
    sawAny = true
    onFix?.({ lat: fix.lat, lon: fix.lon, source, place: fix.place || null })
  }

  function accept(pos) {
    const fix = roundToKm(pos?.coords?.latitude, pos?.coords?.longitude)
    if (fix) deliver(fix, 'device', pos?.coords?.accuracy)
  }

  // Arm the fallbacks first. A cached device fix can arrive inside
  // watchPosition, and that has to be able to cancel these timers.
  const delay = geo ? networkDelayMs : 0
  timers.push(setTimeout(async () => {
    if (cancelled || sawDevice || settledFail) return
    const fix = await networkLookup()
    if (cancelled || sawDevice || settledFail) return
    if (fix) deliver(fix, 'network')
    else if (!geo) fail(2)
  }, delay))

  timers.push(setTimeout(() => {
    clearWatches()
    if (!sawAny && !settledFail && !cancelled) fail(geo ? 3 : 2)
  }, giveUpMs))

  if (geo) {
    // watchPosition, not getCurrentPosition: on macOS the one-shot call often
    // reports a timeout even when a fix arrives a moment later.
    // High accuracy uses Wi-Fi / GPS ("where I am"). A coarse request is only
    // city-level and was the one timing out.
    try {
      const id = geo.watchPosition(accept, (err) => {
        if (err?.code === 1) fail(1)
      }, {
        enableHighAccuracy: true,
        maximumAge: 15000,
        timeout: 20000,
      })
      watchIds.push(id)
    } catch {
      // Geolocation threw; the network lookup above still runs.
    }
  }

  // Already blocked: don't wait, and don't substitute a network guess.
  const permQuery = nav?.permissions?.query?.({ name: 'geolocation' })
  if (permQuery?.then) {
    permQuery.then((status) => {
      if (status?.state === 'denied') fail(1)
    }).catch(() => {})
  }

  return function cancel() {
    cancelled = true
    clearWatches()
    clearTimers()
  }
}
