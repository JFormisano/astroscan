// Person C (#5). The full results screen for one solved job.
// Pass the whole job (`job`), or just `result` (demo mode, Person D). Every section only
// renders when its data exists, so a result from any pipeline stage shows something useful
// instead of a blank screen (see lib/resultView.js).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toView } from '../lib/resultView.js'
import ScoreCard from './ScoreCard.jsx'
import SkyOverlay from './SkyOverlay.jsx'
import UnderTheHood from './UnderTheHood.jsx'
import WarningBanner from './WarningBanner.jsx'
import '../styles/flow.css'

export default function ResultView({ job, result }) {
  const view = toView(job ?? { result })
  const [showGhosts, setShowGhosts] = useState(false)
  const [showLabels, setShowLabels] = useState(true)
  // Before matching runs, the solver's detections are all there is to show, so start with them on.
  const [showHood, setShowHood] = useState(!view.analyzed)
  const ghostCount = view.stars.filter((s) => !s.detected).length
  const canShowHood = view.sources.length > 0 || view.analyzed || view.stats != null
  const names = [...view.constellations.map((c) => c.name), ...view.planets.map((p) => p.name)]

  return (
    <main className="flow results">
      <h1>Your sky</h1>
      <WarningBanner warnings={view.warnings} />

      {!view.analyzed && (
        <p className="card">
          We found where your photo points in the sky. Star names, hidden stars and your sky score aren&apos;t
          ready for this photo yet.
        </p>
      )}

      {view.image ? (
        <div className="sky-wrap">
          <SkyOverlay
            result={view}
            showLabels={showLabels && view.analyzed}
            showGhosts={showGhosts}
            showHood={showHood && canShowHood}
          />
        </div>
      ) : (
        view.imageUrl && (
          <div className="sky-wrap">
            <img className="sky" src={view.imageUrl} alt="Your night sky photo" />
          </div>
        )
      )}

      {ghostCount > 0 && (
        <button
          type="button"
          className={`btn btn-ghost-toggle${showGhosts ? ' on' : ''}`}
          aria-pressed={showGhosts}
          onClick={() => setShowGhosts((v) => !v)}
        >
          {showGhosts ? `Showing ${ghostCount} hidden stars` : `Show the ${ghostCount} stars light pollution is hiding`}
        </button>
      )}

      {(view.analyzed || canShowHood) && (
        <div className="toggles">
          {view.analyzed && (
            <label className="switch">
              <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
              Labels
            </label>
          )}
          {canShowHood && (
            <label className="switch">
              <input type="checkbox" checked={showHood} onChange={(e) => setShowHood(e.target.checked)} />
              Under the hood
            </label>
          )}
        </div>
      )}

      {showHood && canShowHood && <UnderTheHood stats={view.stats} showCatalogKey={view.analyzed} />}

      {names.length > 0 && (
        <p className="muted">
          In your photo: <strong>{names.join(', ')}</strong>
        </p>
      )}

      {view.score && <ScoreCard score={view.score} />}
      {/* Matching ran but scoring hasn't (scoring.py not written yet, or it failed for this photo). */}
      {view.analyzed && !view.score && (
        <section className="card" aria-label="Sky quality score">
          <h2>Sky score</h2>
          <p className="muted">
            {view.scoreFailed
              ? "We identified the stars in your photo, but there weren't enough catalog stars in view to work out a 1–9 score. A photo with more open sky usually fixes this."
              : "We identified the stars in your photo, but the 1–9 sky score isn't available for it yet."}
          </p>
        </section>
      )}

      {view.explainer && (
        <section className="card">
          <h2>What this means</h2>
          <p className="explainer">{view.explainer}</p>
        </section>
      )}

      <nav className="next">
        <Link className="btn btn-primary" to="/map">See it on the light pollution map</Link>
        <Link className="btn btn-secondary" to="/light-report">Report a problem light</Link>
        <Link className="btn btn-link" to="/upload">Measure another photo</Link>
      </nav>
    </main>
  )
}
