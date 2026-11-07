// Person C (#12). Shown when a job comes back with status: failed.
// Pass the whole job (`job`), or just `result` for the older demo/fake shape.
// Error codes and their plain-text message/next_step come from Person A (docs/solver-output.md).
import { Link } from 'react-router-dom'
import { toFailure } from '../lib/resultView.js'

const HEADLINES = {
  too_few_stars: 'Too few stars to identify',
  no_match: "We couldn't match these stars",
  solve_timeout: 'This photo took too long to analyze',
  timeout: 'This photo took too long to analyze', // older fake/demo code
  solver_unavailable: 'Star matching is offline right now',
  solve_failed: "We couldn't finish this photo",
  internal_error: "We couldn't finish this photo",
}

// Used only when the backend didn't send a next_step.
const FALLBACK_NEXT = {
  too_few_stars:
    'Seeing very few stars is itself a sign of heavy light pollution. In a dark place, the same photo would show hundreds.',
  no_match: 'The sky may be cloudy or blurry, or the photo may be mostly trees and buildings.',
  solve_timeout: 'Try again, or use a photo with more stars showing.',
  timeout: 'Try again, or use a photo with more stars showing.',
  solver_unavailable: 'Please try again in a few minutes, or try a sample photo.',
}

// Codes where a better photo would help (vs. our service being down).
const PHOTO_PROBLEM = new Set(['too_few_stars', 'no_match', 'solve_timeout', 'timeout'])

export default function FailedSolve({ job, result }) {
  const f = toFailure(job ?? { result })
  const headline = HEADLINES[f.code] ?? f.message ?? "We couldn't read this photo"
  const next = f.nextStep ?? FALLBACK_NEXT[f.code] ?? 'Please try again, or try a different photo.'

  return (
    <main className="flow">
      <h1>{headline}</h1>
      {f.detected != null && (
        <p className="big-stat">
          <strong>{f.detected}</strong> {f.detected === 1 ? 'star' : 'stars'} detected
        </p>
      )}
      <p className={f.code === 'too_few_stars' ? 'card' : 'muted'}>{next}</p>
      {PHOTO_PROBLEM.has(f.code) && (
        <>
          <h2>For a better photo</h2>
          <ul className="tips">
            <li>Use your phone&apos;s Night mode and hold still (or prop the phone up)</li>
            <li>Fill the frame with sky; leave out buildings and trees</li>
            <li>Turn away from streetlights and wait for a clear night</li>
            <li>Point higher in the sky, not at the horizon</li>
          </ul>
        </>
      )}
      <Link className="btn btn-primary" to="/upload">Try another photo</Link>
      <Link className="btn btn-secondary" to="/">Try a sample photo</Link>
    </main>
  )
}
