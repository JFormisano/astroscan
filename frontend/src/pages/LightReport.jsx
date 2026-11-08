// Route: /light-report — Person D (#9).
// Photo (optional) + pin + type of light → a drafted, polite request the user copies and sends
// themselves. The app never sends email.
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createLightReport } from '../api.js'
import LocationPicker from '../components/LocationPicker.jsx'
import { requestLocation } from '../lib/locate.js'
import '../styles/flow.css'
import '../styles/report.css'

// Keys match CATEGORIES / RECIPIENTS in backend/app/routes/light_reports.py.
const CATEGORIES = [
  ['streetlight', 'Streetlight'],
  ['floodlight', 'Floodlight / security light'],
  ['parking', 'Parking lot light'],
  ['building', 'Building or wall light'],
  ['sign', 'Sign or billboard'],
  ['sports', 'Sports field'],
  ['other', 'Something else'],
]
const CONTROLLERS = [
  ['ub', 'UB campus'],
  ['municipal', 'Town or city'],
  ['business', 'A business or home'],
  ['unknown', 'Not sure'],
]
const NOTE_MAX = 500

function geoMessage(code) {
  if (code === 1) return 'Location is off for this site. Tap the map to place the pin instead.'
  return "We couldn't get your location. Tap the map to place the pin instead."
}

function errorMessage(err) {
  if (err.detail) return `${err.detail.message} ${err.detail.next_step || ''}`.trim()
  if (err.status === 0) return "We couldn't reach the server. Check your connection and try again."
  return 'Something went wrong sending your report. Please try again.'
}

async function copyText(text, textarea) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Clipboard API needs HTTPS; fall back to selecting the text box.
    if (!textarea) return false
    textarea.focus()
    textarea.select()
    try {
      return document.execCommand('copy')
    } catch {
      return false
    }
  }
}

function Draft({ report, onAnother }) {
  const [text, setText] = useState(report.drafted_message)
  const [copied, setCopied] = useState(null) // null | true | false
  const boxRef = useRef(null)

  return (
    <main className="flow">
      <h1>Your request is ready</h1>
      <p className="muted">
        Your report is on the map. Copy this message and send it to{' '}
        {report.controller === 'ub' ? 'UB Facilities' : 'whoever controls the light'} by email, web form or
        letter. You can edit it first.
      </p>
      <p className="hint">
        Tip: replace the approximate location with the street address or building name before you send it.
      </p>

      <label className="report-field">
        <span className="sr-only">Drafted message</span>
        <textarea ref={boxRef} className="draft-box" value={text} onChange={(e) => setText(e.target.value)} />
      </label>

      <button
        type="button"
        className="btn btn-primary btn-big"
        onClick={async () => {
          setCopied(await copyText(text, boxRef.current))
          setTimeout(() => setCopied(null), 2500)
        }}
      >
        {copied === true ? 'Copied!' : 'Copy message'}
      </button>
      {copied === false && (
        <p className="alert alert-warn small">Couldn&apos;t copy automatically. Press and hold the text to copy it.</p>
      )}

      <nav className="next">
        <Link className="btn btn-secondary" to="/map">See it on the map</Link>
        <button type="button" className="btn btn-link" onClick={onAnother}>Report another light</button>
      </nav>
    </main>
  )
}

export default function LightReport() {
  const [photo, setPhoto] = useState(null)
  const [preview, setPreview] = useState(null)
  const [spot, setSpot] = useState(null) // { lat, lon }, precise; rounded before sending
  const [geo, setGeo] = useState({ state: 'idle', message: null })
  const [category, setCategory] = useState(null)
  const [controller, setController] = useState('unknown')
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)
  const fileRef = useRef(null)
  const stopLocate = useRef(() => {})

  // Free the photo preview's memory when it changes or the page closes.
  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview])
  useEffect(() => () => stopLocate.current(), [])

  function locate() {
    stopLocate.current()
    setGeo({ state: 'locating', message: null })
    stopLocate.current = requestLocation({
      onFix: (fix) => {
        setSpot({ lat: fix.lat, lon: fix.lon })
        setGeo({ state: 'ok', message: null })
      },
      onFail: (code) => setGeo({ state: 'error', message: geoMessage(code) }),
    })
  }

  function onPhoto(e) {
    const file = e.target.files?.[0] ?? null
    setPhoto(file)
    setPreview(file ? URL.createObjectURL(file) : null)
  }

  function removePhoto() {
    setPhoto(null)
    setPreview(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setSending(true)
    try {
      const saved = await createLightReport({
        // Round on the phone (~1 km) so the precise spot never leaves the device.
        lat: spot.lat.toFixed(2),
        lon: spot.lon.toFixed(2),
        category,
        controller,
        note: note.trim(),
        photo,
      })
      setReport(saved)
      window.scrollTo(0, 0)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  function startOver() {
    removePhoto()
    setCategory(null)
    setController('unknown')
    setNote('')
    setReport(null)
    setError(null)
    window.scrollTo(0, 0)
  }

  if (report) return <Draft report={report} onAnother={startOver} />

  const missing = [!spot && 'a location', !category && 'the type of light'].filter(Boolean)

  return (
    <main className="flow">
      <h1>Report a problem light</h1>
      <p className="muted">
        Tell us about a light that shines into the sky or where it isn&apos;t needed. We&apos;ll add it to the map
        and write a polite request you can send to whoever controls it.
      </p>

      <form onSubmit={submit} className="flow" style={{ padding: 0 }}>
        <section className="card flow" style={{ padding: 14 }}>
          <h2>1. Where is it?</h2>
          {geo.state !== 'ok' && (
            <button type="button" className="btn btn-secondary" onClick={locate} disabled={geo.state === 'locating'}>
              {geo.state === 'locating' ? 'Finding you…' : 'Use my location'}
            </button>
          )}
          {geo.message && <p className="small" style={{ color: 'var(--warn-fg)' }}>{geo.message}</p>}
          <LocationPicker value={spot} onChange={setSpot} />
          <p className="hint">
            {spot ? 'Tap the map to move the pin.' : 'Or tap the map to place the pin.'} Saved to about 1 km.
          </p>
        </section>

        <section className="card flow" style={{ padding: 14 }}>
          <fieldset className="chips">
            <legend>2. What kind of light?</legend>
            {CATEGORIES.map(([key, label]) => (
              <button key={key} type="button" className="chip" aria-pressed={category === key} onClick={() => setCategory(key)}>
                {label}
              </button>
            ))}
          </fieldset>
          <fieldset className="chips">
            <legend>Who controls it?</legend>
            {CONTROLLERS.map(([key, label]) => (
              <button key={key} type="button" className="chip" aria-pressed={controller === key} onClick={() => setController(key)}>
                {label}
              </button>
            ))}
          </fieldset>
        </section>

        <section className="card flow" style={{ padding: 14 }}>
          <h2>3. Photo and note <span className="muted small">(optional)</span></h2>
          {preview ? (
            <>
              <img className="report-photo" src={preview} alt="The light you're reporting" />
              <button type="button" className="btn btn-link" onClick={removePhoto}>Remove photo</button>
            </>
          ) : (
            <label className="btn btn-secondary" style={{ cursor: 'pointer' }}>
              Add a photo of the light
              <input ref={fileRef} type="file" accept="image/jpeg,image/png" onChange={onPhoto} className="sr-only" />
            </label>
          )}
          <p className="hint">Location data is removed from the photo before it&apos;s saved.</p>

          <label className="report-field">
            <span>What&apos;s the problem?</span>
            <textarea
              value={note}
              maxLength={NOTE_MAX}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Unshielded floodlight on the parking garage, on all night, shines into dorm windows"
            />
            <span className="hint" style={{ fontWeight: 400 }}>{note.length}/{NOTE_MAX}</span>
          </label>
        </section>

        {error && <p className="alert alert-error" role="alert">{error}</p>}

        <button type="submit" className="btn btn-primary btn-big" disabled={sending || missing.length > 0}>
          {sending ? 'Writing your request…' : 'Create my request'}
        </button>
        {missing.length > 0 && <p className="hint" style={{ textAlign: 'center' }}>Add {missing.join(' and ')} to continue.</p>}
        <p className="small muted" style={{ textAlign: 'center' }}>We never send anything for you. You decide whether to send it.</p>
      </form>
    </main>
  )
}
