// Route: /demo/:name — demo mode (#11), Person D.
// Loads a cached, pre-solved result and shows it on Person C's results screen, unchanged.
// No solver, no database, no AI call: it must work on a judge's phone every time.
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDemo } from '../api.js'
import FailedSolve from '../components/FailedSolve.jsx'
import ResultView from '../components/ResultView.jsx'
import { DEMO_SAMPLES } from '../demoSamples.js'
import '../styles/flow.css'

const bannerStyle = {
  maxWidth: 480,
  margin: '0 auto',
  padding: '12px 16px 0',
}
const pillStyle = {
  background: 'rgba(8, 12, 22, 0.82)',
  border: '1px solid rgba(228, 160, 74, 0.32)',
  borderRadius: 12,
  padding: '10px 12px',
  fontSize: '0.9rem',
  lineHeight: 1.45,
  color: '#f6f3ec',
}

function SampleBanner({ name }) {
  const current = DEMO_SAMPLES.find((s) => s.name === name)
  const others = DEMO_SAMPLES.filter((s) => s.name !== name)
  return (
    <div style={bannerStyle}>
      <p style={{ ...pillStyle, margin: 0 }} role="note">
        <strong>Sample photo{current ? `: ${current.label}` : ''}.</strong> A pre-analyzed example, not your sky.
        {others.length > 0 && (
          <>
            {' '}Compare:{' '}
            {others.map((s, i) => (
              <span key={s.name}>
                {i > 0 && ' · '}
                <Link to={`/demo/${s.name}`} style={{ color: '#e4a04a' }}>{s.label}</Link>
              </span>
            ))}
          </>
        )}
      </p>
    </div>
  )
}

export default function Demo() {
  const { name } = useParams()
  const [loaded, setLoaded] = useState(null) // { name, job }
  const [failure, setFailure] = useState(null) // { name, kind: 'notfound' | 'other' }
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let stopped = false
    getDemo(name)
      .then((job) => !stopped && setLoaded({ name, job }))
      .catch((err) => !stopped && setFailure({ name, kind: err.status === 404 ? 'notfound' : 'other' }))
    return () => {
      stopped = true
    }
  }, [name, attempt])

  // Only use state that belongs to the sample in the URL (switching samples reuses this page).
  const job = loaded?.name === name ? loaded.job : null
  const error = failure?.name === name ? failure.kind : null

  if (error === 'notfound') {
    return (
      <main className="flow">
        <h1>We can&apos;t find that sample</h1>
        <p className="muted">This sample photo doesn&apos;t exist. Try one of ours instead.</p>
        {DEMO_SAMPLES.map((s) => (
          <Link key={s.name} className="btn btn-secondary" to={`/demo/${s.name}`}>{s.label}</Link>
        ))}
        <Link className="btn btn-link" to="/">Home</Link>
      </main>
    )
  }
  if (error) {
    return (
      <main className="flow">
        <h1>Couldn&apos;t load the sample</h1>
        <p className="muted">Check your connection and try again.</p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setFailure(null)
            setAttempt((a) => a + 1)
          }}
        >
          Try again
        </button>
        <Link className="btn btn-link" to="/">Home</Link>
      </main>
    )
  }
  if (!job) {
    return (
      <main className="flow">
        <div className="spinner" aria-label="Loading the sample photo" />
      </main>
    )
  }

  return (
    <>
      <SampleBanner name={name} />
      {job.status === 'failed' ? <FailedSolve result={job.result} /> : <ResultView result={job.result} />}
    </>
  )
}
