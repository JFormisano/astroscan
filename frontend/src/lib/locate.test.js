import assert from 'node:assert/strict'
import test from 'node:test'
import { lookupNetworkLocation, requestLocation, roundToKm } from './locate.js'

test('roundToKm keeps about a kilometre and rejects impossible coordinates', () => {
  assert.deepEqual(roundToKm(42.8864, -78.8784), { lat: 42.89, lon: -78.88 })
  assert.deepEqual(roundToKm('43.0014', '-78.7896'), { lat: 43, lon: -78.79 })
  assert.equal(roundToKm(90, 180).lat, 90)
  assert.equal(roundToKm(90, 180).lon, 180)
  assert.equal(roundToKm(90.1, 0), null)
  assert.equal(roundToKm(0, -180.1), null)
  assert.equal(roundToKm('nope', 1), null)
})

test('lookupNetworkLocation skips a dead service and reads string coordinates', async () => {
  const calls = []
  const fetchImpl = async (url) => {
    calls.push(String(url))
    if (String(url).includes('geojs')) return { ok: false, json: async () => ({}) }
    return {
      ok: true,
      json: async () => ({ success: true, latitude: '42.8864', longitude: '-78.8784', city: 'Buffalo', region: 'New York' }),
    }
  }
  assert.deepEqual(await lookupNetworkLocation(fetchImpl), {
    lat: 42.89,
    lon: -78.88,
    place: 'Buffalo, New York',
  })
  assert.equal(calls.length, 2)
})

test('requestLocation rounds a device fix and does not ask the network', async () => {
  let lookups = 0
  let stop = () => {}
  const fix = await new Promise((resolve, reject) => {
    stop = requestLocation({
      nav: {
        geolocation: {
          watchPosition(success) {
            success({ coords: { latitude: 43.0014, longitude: -78.7896, accuracy: 40 } })
            return 1
          },
          clearWatch() {},
        },
      },
      onFix: resolve,
      onFail: reject,
      networkDelayMs: 0,
      giveUpMs: 50,
      networkLookup: async () => {
        lookups += 1
        return { lat: 0, lon: 0 }
      },
    })
  })
  stop()
  await new Promise((r) => setTimeout(r, 20))
  assert.equal(fix.source, 'device')
  assert.deepEqual({ lat: fix.lat, lon: fix.lon }, { lat: 43, lon: -78.79 })
  assert.equal(lookups, 0)
})

test('requestLocation uses the network when the device request times out', async () => {
  let stop = () => {}
  const fix = await new Promise((resolve, reject) => {
    stop = requestLocation({
      nav: {
        geolocation: {
          watchPosition(_success, error) {
            error({ code: 3 })
            return 4
          },
          clearWatch() {},
        },
      },
      onFix: resolve,
      onFail: reject,
      networkDelayMs: 0,
      giveUpMs: 1000,
      networkLookup: async () => ({ lat: 42.89, lon: -78.88 }),
    })
  })
  stop()
  assert.equal(fix.source, 'network')
  assert.deepEqual({ lat: fix.lat, lon: fix.lon }, { lat: 42.89, lon: -78.88 })
})

test('requestLocation does not guess from the network when location is blocked', async () => {
  let lookups = 0
  let stop = () => {}
  const code = await new Promise((resolve) => {
    stop = requestLocation({
      nav: {
        geolocation: {
          watchPosition(_success, error) {
            error({ code: 1 })
            return 2
          },
          clearWatch() {},
        },
        permissions: { async query() { return { state: 'denied' } } },
      },
      onFix: () => resolve('fix'),
      onFail: resolve,
      networkDelayMs: 0,
      giveUpMs: 50,
      networkLookup: async () => {
        lookups += 1
        return { lat: 1, lon: 2 }
      },
    })
  })
  stop()
  await new Promise((r) => setTimeout(r, 20))
  assert.equal(code, 1)
  assert.equal(lookups, 0)
})
