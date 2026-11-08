// Route: /map — shared light pollution map. Owner: Person D (#8).
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMap } from '../api.js'
import MapView from '../components/MapView.jsx'
import { REPORT_COLOR, scoreColor } from '../components/mapColors.js'
import '../styles/flow.css'

const LEGEND = [
  { color: scoreColor(2), label: 'Dark sky (1–3)' },
  { color: scoreColor(5), label: 'Moderate (4–6)' },
  { color: scoreColor(8), label: 'Bright (7–9)' },
  { color: scoreColor(null), label: 'Too few stars to score' },
  { color: REPORT_COLOR, label: 'Light report' },
]

export default function Map() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    getMap()
      .then((result) => {
        setData(result)
        setError(null)
      })
      .catch(() => setError("We couldn't load the map. Check your connection and try again."))
  }, [])

  useEffect(load, [load])

  const retry = () => {
    setError(null)
    load()
  }

  const count = data ? data.measurements.length : 0

  return (
    <main className="flow">
      <h1>Light pollution map</h1>
      <p className="muted">
        {data
          ? `${count} sky measurement${count === 1 ? '' : 's'} and ${data.light_reports.length} light report${data.light_reports.length === 1 ? '' : 's'}. Tap a dot for details.`
          : 'Every photo adds a point to this map.'}
      </p>

      {error && (
        <div className="alert alert-error" role="alert">
          <p>{error}</p>
          <button type="button" className="btn btn-secondary" onClick={retry}>Try again</button>
        </div>
      )}

      {!data && !error && <p>Loading map…</p>}

      {data && (
        <div className="map-frame">
          <MapView measurements={data.measurements} reports={data.light_reports} />
        </div>
      )}

      <ul className="map-legend">
        {LEGEND.map((item) => (
          <li key={item.label}>
            <span aria-hidden="true" style={{ background: item.color }} />
            {item.label}
          </li>
        ))}
      </ul>

      <p className="hint">
        Scores are Bortle-style estimates of your sky as your phone saw it. Locations are rounded to about 1 km.
      </p>

      <Link className="btn btn-link" to="/upload">Measure your sky</Link>
    </main>
  )
}
