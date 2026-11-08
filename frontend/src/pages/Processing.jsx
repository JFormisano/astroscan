// Route: /processing/:jobId — Person C (#1 processing page).
// Polls the job until solved/failed, then replaces itself with /results/:jobId.
// The job id is in the URL, so a refresh or a locked phone picks up where it left off.
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getMeasurement } from '../api.js'
import '../styles/flow.css'

const STEPS = [
  { key: 'queued', label: 'Photo uploaded' },
  { key: 'detecting', label: 'Finding stars…' },
  { key: 'solving', label: 'Matching star patterns…' },
  { key: 'matching', label: 'Naming stars and constellations…' },
  { key: 'scoring', label: 'Measuring your sky…' },
]
const POLL_MS = 2000
const SLOW_MS = 90 * 1000 // show "taking a while" note
const GIVE_UP_MS = 6 * 60 * 1000 // the backend should fail first; this is a safety net

export default function Processing() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [step, setStep] = useState('queued')
  const [offline, setOffline] = useState(false)
  const [notFound, setNotFound] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    let timer = null
    let stopped = false
    const start = Date.now()

    async function poll() {
      if (stopped) return
      clearTimeout(timer)
      setElapsed(Date.now() - start)
      try {
        const job = await getMeasurement(jobId)
        if (stopped) return
        setOffline(false)
        if (job.status === 'solved' || job.status === 'failed') {
          navigate(`/results/${encodeURIComponent(jobId)}`, { replace: true })
          return
        }
        if (job.step) setStep(job.step)
      } catch (err) {
        if (stopped) return
        if (err.status === 404) {
          setNotFound(true)
          return
        }
        setOffline(true) // keep trying: phones drop connection when locked
      }
      if (Date.now() - start < GIVE_UP_MS) timer = setTimeout(poll, POLL_MS)
    }

    // Timers pause while the phone is locked; check right away when it wakes up.
    const onVisible = () => document.visibilityState === 'visible' && poll()
    document.addEventListener('visibilitychange', onVisible)
    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [jobId, navigate])

  if (notFound) {
    return (
      <main className="flow">
        <h1>We can&apos;t find that photo</h1>
        <p className="muted">This link may be old or mistyped.</p>
        <Link className="btn btn-primary" to="/upload">Upload a photo</Link>
      </main>
    )
  }

  if (elapsed >= GIVE_UP_MS) {
    return (
      <main className="flow">
        <h1>This is taking too long</h1>
        <p className="muted">
          We couldn&apos;t finish analyzing your photo. The star-matching service may be busy. Try again in a few
          minutes, or try a different photo.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>Check again</button>
        <Link className="btn btn-secondary" to="/upload">Try another photo</Link>
        <Link className="btn btn-link" to="/">Try a sample photo</Link>
      </main>
    )
  }

  // Unknown steps (the upload route currently sets "Reading photo") count as the first step.
  const known = STEPS.findIndex((s) => s.key === step)
  const current = known === -1 ? 0 : known

  return (
    <main className="flow">
      <h1>Reading your sky</h1>
      <div className="spinner" aria-hidden="true" />
      <ol className="steps" aria-live="polite">
        {STEPS.map((s, i) => (
          <li key={s.key} className={i < current ? 'done' : i === current ? 'active' : ''}>
            <span className="dot" aria-hidden="true">{i < current ? '✓' : ''}</span>
            {s.label}
          </li>
        ))}
      </ol>
      {offline && <p className="alert alert-warn">Lost connection. Still trying…</p>}
      {elapsed >= SLOW_MS && !offline && (
        <p className="muted small">Taking a while. Some photos take a few minutes. You can lock your phone; this page will catch up.</p>
      )}
      <p className="muted small">
        Bookmark this page to come back later: your result will be at this address.
      </p>
    </main>
  )
}
