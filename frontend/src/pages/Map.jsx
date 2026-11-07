// Route: /map — shared light pollution map. Owner: Person D (#8).
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMap } from '../api.js'
import MapView from '../components/MapView.jsx'
import { REPORT_COLOR, scoreColor } from '../components/mapColors.js'

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
    <main>
      <h1 style={{ marginBottom: 4 }}>Light pollution map</h1>
      <p style={{ marginTop: 0, opacity: 0.8 }}>
        {data
          ? `${count} sky measurement${count === 1 ? '' : 's'} and ${data.light_reports.length} light report${data.light_reports.length === 1 ? '' : 's'}. Tap a dot for details.`
          : 'Every photo adds a point to this map.'}
      </p>

      {error && (
        <div role="alert" style={{ padding: 12, borderRadius: 8, background: '#3a1d24', marginBottom: 12 }}>
          <p style={{ margin: '0 0 8px' }}>{error}</p>
          <button type="button" onClick={retry}>Try again</button>
        </div>
      )}

      {!data && !error && <p>Loading map…</p>}

      {data && <MapView measurements={data.measurements} reports={data.light_reports} />}

      <ul style={{ listStyle: 'none', padding: 0, margin: '12px 0', display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 14 }}>
        {LEGEND.map((item) => (
          <li key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span aria-hidden="true" style={{ width: 12, height: 12, borderRadius: '50%', background: item.color, border: '1px solid #fff' }} />
            {item.label}
          </li>
        ))}
      </ul>

      <p style={{ fontSize: 13, opacity: 0.7 }}>
        Scores are Bortle-style estimates of your sky as your phone saw it. Locations are rounded to about 1 km.
      </p>

      <p>
        <Link to="/upload" style={{ color: '#8ab4ff' }}>Measure your sky</Link>
      </p>
    </main>
  )
}
