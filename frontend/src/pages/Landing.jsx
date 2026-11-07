// Route: / — Person D. Two ways in: measure your own sky, or try a sample photo (#11),
// so a judge without a night photo can still see the whole app on their own phone.
import { Link } from 'react-router-dom'
import { DEFAULT_DEMO } from '../demoSamples.js'
import '../styles/flow.css'

export default function Landing() {
  return (
    <main className="flow">
      <h1 style={{ fontSize: '2rem', marginTop: 24 }}>AstroScan</h1>
      <p style={{ fontSize: '1.15rem' }}>
        See the stars light pollution is hiding.
      </p>
      <p className="muted">
        Upload a night-sky photo from your phone. We name the stars and constellations in it, score how
        bright your sky is from 1 to 9, and show you the stars you&apos;re missing.
      </p>

      <Link className="btn btn-primary btn-big" to="/upload">Measure your sky</Link>
      <Link className="btn btn-secondary btn-big" to={`/demo/${DEFAULT_DEMO}`}>Try a sample photo</Link>
      <p className="hint" style={{ textAlign: 'center' }}>No night photo? The sample works right now.</p>

      <section className="card">
        <h2>How it works</h2>
        <ol className="tips" style={{ marginTop: 8 }}>
          <li>Take a Night mode photo of the sky, away from bright lights in the frame</li>
          <li>Upload it here and confirm where you took it</li>
          <li>See your score, the hidden &quot;ghost&quot; stars, and add your sky to the shared map</li>
        </ol>
      </section>

      <nav className="next">
        <Link className="btn btn-link" to="/map">See the light pollution map</Link>
        <Link className="btn btn-link" to="/light-report">Report a problem light</Link>
      </nav>

      <p className="small muted" style={{ textAlign: 'center' }}>
        Free, no account. Photo location data is removed and your location is rounded to about 1 km.
      </p>
    </main>
  )
}
