// Person C (#12). Shown when the backend returns status: failed.
import { Link } from 'react-router-dom'

const HEADLINES = {
  too_few_stars: 'Too few stars to identify',
  no_match: "We couldn't match these stars",
  timeout: 'This photo took too long to analyze',
}

export default function FailedSolve({ result }) {
  const reason = result?.reason
  const count = result?.stars_detected
  return (
    <main className="flow">
      <h1>{HEADLINES[reason] ?? "We couldn't read this photo"}</h1>
      {count != null && (
        <p className="big-stat">
          <strong>{count}</strong> {count === 1 ? 'star' : 'stars'} detected
        </p>
      )}
      {reason === 'too_few_stars' && (
        <p className="card">
          Seeing very few stars is itself a sign of heavy light pollution. In a dark place, the same photo would show
          hundreds.
        </p>
      )}
      {reason === 'timeout' && (
        <p className="muted">The star-matching service may be busy. Try again in a few minutes.</p>
      )}
      {reason === 'no_match' && (
        <p className="muted">We found stars but couldn&apos;t work out which part of the sky they are.</p>
      )}
      <h2>For a better photo</h2>
      <ul className="tips">
        <li>Use your phone&apos;s Night mode and hold still (or prop the phone up)</li>
        <li>Fill the frame with sky; leave out buildings and trees</li>
        <li>Turn away from streetlights and wait for a clear night</li>
        <li>Point higher in the sky, not at the horizon</li>
      </ul>
      <Link className="btn btn-primary" to="/upload">Try another photo</Link>
      <Link className="btn btn-secondary" to="/">Try a sample photo</Link>
    </main>
  )
}
