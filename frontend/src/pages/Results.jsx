// Route: /results/:jobId — Person C (#5, #12). Fetches the job once and renders it.
// Demo mode (Person D) can render the same view with <ResultView result={...} />.
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getMeasurement } from '../api.js'
import FailedSolve from '../components/FailedSolve.jsx'
import ResultView from '../components/ResultView.jsx'
import '../styles/flow.css'

export default function Results() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let stopped = false
    getMeasurement(jobId)
      .then((j) => {
        if (stopped) return
        if (j.status === 'pending') navigate(`/processing/${encodeURIComponent(jobId)}`, { replace: true })
        else setJob(j)
      })
      .catch((err) => !stopped && setError(err.status === 404 ? 'notfound' : 'other'))
    return () => {
      stopped = true
    }
  }, [jobId, navigate, attempt])

  if (error === 'notfound') {
    return (
      <main className="flow">
        <h1>We can&apos;t find that result</h1>
        <p className="muted">This link may be old or mistyped.</p>
        <Link className="btn btn-primary" to="/upload">Upload a photo</Link>
      </main>
    )
  }
  if (error) {
    return (
      <main className="flow">
        <h1>Couldn&apos;t load your result</h1>
        <p className="muted">Check your connection and try again.</p>
        <button type="button" className="btn btn-primary" onClick={() => {
            setError(null)
            setAttempt((a) => a + 1)
          }}>Try again</button>
      </main>
    )
  }
  if (!job) {
    return (
      <main className="flow">
        <div className="spinner" aria-label="Loading your result" />
      </main>
    )
  }
  if (job.status === 'failed') return <FailedSolve job={job} />
  return <ResultView job={job} />
}
