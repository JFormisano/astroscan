// Leaflet map of sky measurements and light reports. Owner: Person D (#8).
// Plain Leaflet (already a dependency) driven by refs, no react-leaflet needed.
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css' // required, or the tiles render scrambled
import { REPORT_COLOR, scoreColor } from './mapColors.js'

const BUFFALO = [42.93, -78.8]

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ))
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

function measurementPopup(m) {
  const head = m.score == null
    ? '<strong>Too few stars to score</strong><br>Very few visible stars is itself a sign of heavy light pollution.'
    : `<strong>Sky score ${m.score}/9</strong> (Bortle-style estimate)<br>${escapeHtml(m.confidence)} confidence`
  const when = formatTime(m.taken_at_utc)
  return `${head}${when ? `<br><small>${escapeHtml(when)}</small>` : ''}${m.is_demo ? '<br><small>Sample data</small>' : ''}`
}

function reportPopup(r) {
  const note = r.note ? `<br>${escapeHtml(r.note)}` : ''
  return `<strong>Light report: ${escapeHtml(r.category_label || r.category || 'light')}</strong>${note}`
}

export default function MapView({ measurements = [], reports = [] }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const layerRef = useRef(null)

  // Create the map once.
  useEffect(() => {
    const map = L.map(containerRef.current).setView(BUFFALO, 10)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)
    layerRef.current = L.layerGroup().addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      layerRef.current = null
    }
  }, [])

  // Redraw the points whenever the data changes.
  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return
    layer.clearLayers()

    // circleMarker instead of L.marker: the default pin images break under Vite,
    // and colored circles show the score at a glance.
    measurements.forEach((m) => {
      L.circleMarker([m.lat, m.lon], {
        radius: 11, color: '#fff', weight: 1.5, fillColor: scoreColor(m.score), fillOpacity: 0.9,
      }).bindPopup(measurementPopup(m)).addTo(layer)
    })
    reports.forEach((r) => {
      L.circleMarker([r.lat, r.lon], {
        radius: 7, color: '#fff', weight: 1.5, fillColor: REPORT_COLOR, fillOpacity: 1,
      }).bindPopup(reportPopup(r)).addTo(layer)
    })

    const points = [...measurements, ...reports].map((p) => [p.lat, p.lon])
    if (points.length > 0) map.fitBounds(points, { padding: [30, 30], maxZoom: 13 })
  }, [measurements, reports])

  return (
    <div
      ref={containerRef}
      role="region"
      aria-label="Light pollution map"
      style={{ height: '65vh', minHeight: 320, width: '100%', borderRadius: 12 }}
    />
  )
}
