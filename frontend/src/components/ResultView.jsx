// Person C (#5). The full results screen for one solved result.
// Pages pass a result in the agreed schema; demo mode (Person D) can reuse this as-is.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import ScoreCard from './ScoreCard.jsx'
import SkyOverlay from './SkyOverlay.jsx'
import UnderTheHood from './UnderTheHood.jsx'
import WarningBanner from './WarningBanner.jsx'
import '../styles/flow.css'

export default function ResultView({ result }) {
  const [showGhosts, setShowGhosts] = useState(false)
  const [showLabels, setShowLabels] = useState(true)
  const [showHood, setShowHood] = useState(false)
  const ghostCount = (result.stars ?? []).filter((s) => !s.detected).length
  const names = [
    ...(result.constellations ?? []).map((c) => c.name),
    ...(result.planets ?? []).map((p) => p.name),
  ]

  return (
    <main className="flow results">
      <h1>Your sky</h1>
      <WarningBanner warnings={result.warnings} />

      <div className="sky-wrap">
        <SkyOverlay result={result} showLabels={showLabels} showGhosts={showGhosts} showHood={showHood} />
      </div>

      <button
        type="button"
        className={`btn btn-ghost-toggle${showGhosts ? ' on' : ''}`}
        aria-pressed={showGhosts}
        onClick={() => setShowGhosts((v) => !v)}
      >
        {showGhosts ? `Showing ${ghostCount} hidden stars` : `Show the ${ghostCount} stars light pollution is hiding`}
      </button>

      <div className="toggles">
        <label className="switch">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Labels
        </label>
        <label className="switch">
          <input type="checkbox" checked={showHood} onChange={(e) => setShowHood(e.target.checked)} />
          Under the hood
        </label>
      </div>

      {showHood && <UnderTheHood stats={result.stats} />}

      {names.length > 0 && (
        <p className="muted">
          In your photo: <strong>{names.join(', ')}</strong>
        </p>
      )}

      <ScoreCard score={result.score} />

      {result.explainer && (
        <section className="card">
          <h2>What this means</h2>
          <p className="explainer">{result.explainer}</p>
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
