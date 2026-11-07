// Route: /upload — Person C (#1 upload flow, frontend).
// Pick photo → confirm time + location → upload → /processing/:jobId
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createMeasurement } from '../api.js'
import { readExifTime } from '../lib/exif.js'
import '../styles/flow.css'

const MAX_BYTES = 15 * 1024 * 1024

// Validate before reading anything. Returns an error message or null.
function checkFile(file) {
  const name = file.name.toLowerCase()
  if (/heic|heif/.test(file.type) || /\.(heic|heif)$/.test(name)) {
    return "iPhone HEIC photos aren't supported yet. Pick the photo again and choose JPEG if your phone asks, or set Settings → Camera → Formats → Most Compatible, then take a new photo."
  }
  if (!['image/jpeg', 'image/png'].includes(file.type) && !/\.(jpe?g|png)$/.test(name)) {
    return 'Please choose a JPEG or PNG photo.'
  }
  if (file.size > MAX_BYTES) {
    return `That photo is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 15 MB. Try a smaller copy, or export it at a lower quality.`
  }
  return null
}

// <input type="datetime-local"> wants local time as "YYYY-MM-DDTHH:MM".
function toLocalInput(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function geoMessage(code) {
  if (code === 1) return 'Location is blocked. Allow it in your browser settings, or type where you took the photo below.'
  if (code === 3) return "Finding your location took too long. Try again, or type it below."
  return "We couldn't get your location. Type where you took the photo below."
}

export default function Upload() {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [fileError, setFileError] = useState(null)
  const [timeText, setTimeText] = useState('')
  const [timeSource, setTimeSource] = useState(null) // 'exif' | 'exif-no-zone' | 'none'
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [geo, setGeo] = useState({ state: 'idle', message: null })
  const [sending, setSending] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  function locate() {
    if (!('geolocation' in navigator)) {
      setGeo({ state: 'error', message: geoMessage(2) })
      return
    }
    setGeo({ state: 'locating', message: null })
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Round in the browser (~1 km) so the precise location never leaves the phone.
        setLat(pos.coords.latitude.toFixed(2))
        setLon(pos.coords.longitude.toFixed(2))
        setGeo({ state: 'ok', message: null })
      },
      (err) => setGeo({ state: 'error', message: geoMessage(err.code) }),
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 10 * 60 * 1000 },
    )
  }

  async function onPick(e) {
    const picked = e.target.files?.[0]
    e.target.value = '' // allow re-picking the same file
    if (!picked) return
    setSubmitError(null)
    const problem = checkFile(picked)
    if (problem) {
      setFileError(problem)
      return
    }
    setFileError(null)
    const exif = await readExifTime(picked)
    if (exif) {
      setTimeText(toLocalInput(exif.date))
      setTimeSource(exif.hadOffset ? 'exif' : 'exif-no-zone')
    } else {
      setTimeText(toLocalInput(new Date()))
      setTimeSource('none')
    }
    setFile(picked)
    setPreviewUrl(URL.createObjectURL(picked))
    if (geo.state !== 'ok') locate()
  }

  function reset() {
    setFile(null)
    setPreviewUrl(null)
    setSubmitError(null)
  }

  const latNum = Number.parseFloat(lat)
  const lonNum = Number.parseFloat(lon)
  const takenAt = timeText ? new Date(timeText) : null // parsed as device-local time
  const problems = []
  if (!(latNum >= -90 && latNum <= 90) || !(lonNum >= -180 && lonNum <= 180)) {
    problems.push('Add the location (latitude −90 to 90, longitude −180 to 180).')
  }
  if (!takenAt || Number.isNaN(takenAt.getTime())) problems.push('Add when the photo was taken.')

  async function onSubmit(e) {
    e.preventDefault()
    if (problems.length || sending) return
    if (takenAt.getTime() > Date.now() + 5 * 60 * 1000) {
      setSubmitError("That time is in the future. Check when you took the photo.")
      return
    }
    setSending(true)
    setSubmitError(null)
    try {
      const { job_id } = await createMeasurement(file, {
        lat: Math.round(latNum * 100) / 100,
        lon: Math.round(lonNum * 100) / 100,
        takenAt,
      })
      navigate(`/processing/${encodeURIComponent(job_id)}`)
    } catch (err) {
      setSending(false)
      // The backend's own wording first (app/errors.py: message + next step), then our fallbacks.
      if (err.userMessage) setSubmitError([err.userMessage, err.nextStep].filter(Boolean).join(' '))
      else if (err.status === 413) setSubmitError('That photo is too large for the server. Try a smaller copy.')
      else if (err.status === 415) setSubmitError("The server couldn't read that file type. Try a JPEG.")
      else if (err.status === 0) setSubmitError("Couldn't reach the server. Check your connection and try again.")
      else setSubmitError('Something went wrong uploading your photo. Please try again.')
    }
  }

  if (!file) {
    return (
      <main className="flow">
        <h1>Measure your sky</h1>
        <p className="muted">
          Take a photo of the night sky with your phone&apos;s <strong>Night mode</strong>, holding it steady
          (or propped up), pointed away from streetlights. Then upload it here.
        </p>
        <button type="button" className="btn btn-primary btn-big" onClick={() => inputRef.current?.click()}>
          Choose a night sky photo
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png"
          onChange={onPick}
          hidden
        />
        {fileError && <p className="alert alert-error" role="alert">{fileError}</p>}
        <ul className="tips">
          <li>JPEG or PNG, up to 15 MB</li>
          <li>More sky, fewer buildings = better results</li>
          <li>We remove all location data from your photo before saving it</li>
        </ul>
        <p className="muted small">
          No night photo handy? <Link to="/">Try a sample photo</Link>.
        </p>
      </main>
    )
  }

  return (
    <main className="flow">
      <h1>Check the details</h1>
      <img className="preview" src={previewUrl} alt="Your night sky photo" />
      <form onSubmit={onSubmit} className="confirm">
        <fieldset>
          <legend>When did you take it?</legend>
          <input
            type="datetime-local"
            value={timeText}
            onChange={(e) => setTimeText(e.target.value)}
            required
          />
          <p className="hint">
            {timeSource === 'exif' && 'Read from your photo.'}
            {timeSource === 'exif-no-zone' && "Read from your photo, in this phone's time zone. Change it if you took it somewhere else."}
            {timeSource === 'none' && "We couldn't find a time in this photo. Set when you took it; the time matters for finding planets and the Moon."}
          </p>
        </fieldset>

        <fieldset>
          <legend>Where did you take it?</legend>
          {geo.state === 'locating' && <p className="hint">Finding your location…</p>}
          {geo.state === 'ok' && <p className="hint">Using your current location. Change it if you took the photo somewhere else.</p>}
          {geo.message && <p className="alert alert-warn">{geo.message}</p>}
          <div className="row">
            <label>
              Latitude
              <input inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="43.00" />
            </label>
            <label>
              Longitude
              <input inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="-78.79" />
            </label>
          </div>
          {geo.state !== 'locating' && (
            <button type="button" className="btn btn-link" onClick={locate}>
              Use my current location
            </button>
          )}
          <p className="hint">Rounded to about 1 km. That&apos;s the only location we keep.</p>
        </fieldset>

        {problems.length > 0 && (
          <ul className="problems">
            {problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
        {submitError && <p className="alert alert-error" role="alert">{submitError}</p>}

        <button type="submit" className="btn btn-primary btn-big" disabled={problems.length > 0 || sending}>
          {sending ? 'Uploading…' : 'Analyze my sky'}
        </button>
        <button type="button" className="btn btn-secondary" onClick={reset} disabled={sending}>
          Choose a different photo
        </button>
      </form>
    </main>
  )
}
