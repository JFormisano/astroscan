// Route: / — Person D. Opens in a telescope. Tap constellations to look around,
// then zoom into the title. Skip jumps straight to upload / sample photo (#11).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Eyepiece from '../components/Eyepiece.jsx'
import StarField from '../components/StarField.jsx'
import { DEFAULT_DEMO } from '../demoSamples.js'
import '../styles/flow.css'
import '../styles/landing.css'

function motionReduced() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function Landing() {
  const [reduced, setReduced] = useState(motionReduced)
  const [open, setOpen] = useState(motionReduced)
  const [instant, setInstant] = useState(motionReduced)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => {
      if (!mq.matches) return
      setReduced(true)
      setInstant(true)
      setOpen(true)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  function skip() {
    setInstant(true)
    setOpen(true)
  }

  function zoomIn() {
    setInstant(false)
    setOpen(true)
  }

  const className = [
    'eyepiece',
    open ? 'is-open' : '',
    instant ? 'is-instant' : '',
  ].filter(Boolean).join(' ')

  return (
    <main className={className}>
      <StarField animate={!reduced} />
      <div className="veil" aria-hidden="true" />
      <div className="reticle" aria-hidden="true">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="47" fill="none" stroke="rgba(246, 243, 236, 0.85)" strokeWidth="0.6" />
        </svg>
      </div>
      {open ? null : <Eyepiece onEnter={zoomIn} onSkip={skip} />}
      <div className="landing-copy" inert={open ? undefined : true}>
        <div className="hero">
          <h1>AstroScan</h1>
          <p className="pitch">See the stars light pollution is hiding</p>
          <Link className="btn btn-primary btn-big" to="/upload">Upload a night photo</Link>
          <Link className="btn btn-secondary btn-big" to={`/demo/${DEFAULT_DEMO}`}>Try a sample photo</Link>
        </div>
        <section className="card more">
          <h2>How it works</h2>
          <p className="muted">
            Upload a night-sky photo from your phone. We name the stars and constellations in it, score how
            bright your sky is from 1 to 9, and show you the stars you&apos;re missing.
          </p>
          <ol className="tips">
            <li>Take a Night mode photo of the sky, away from bright lights in the frame</li>
            <li>Upload it here and confirm where you took it</li>
            <li>See your score, the hidden &quot;ghost&quot; stars, and add your sky to the shared map</li>
          </ol>
        </section>
        <nav className="next">
          <Link className="btn btn-link" to="/map">See the light pollution map</Link>
          <Link className="btn btn-link" to="/light-report">Report a problem light</Link>
        </nav>
        <p className="small privacy">
          Free, no account. Photo location data is removed and your location is rounded to about 1 km.
        </p>
      </div>
    </main>
  )
}
