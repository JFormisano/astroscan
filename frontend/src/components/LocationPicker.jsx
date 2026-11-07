// Small Leaflet map for placing a pin: tap to move it. Owner: Person D (#9).
// A circle marker instead of L.marker: the default pin images break under Vite.
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { REPORT_COLOR } from './mapColors.js'

const BUFFALO = [42.93, -78.8]

export default function LocationPicker({ value, onChange }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const onChangeRef = useRef(onChange)

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    const map = L.map(containerRef.current).setView(BUFFALO, 11)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)
    map.on('click', (e) => onChangeRef.current({ lat: e.latlng.lat, lon: e.latlng.lng }))
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      markerRef.current = null
    }
  }, [])

  // Move (or create) the pin and center on it whenever the value changes.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !value) return
    const pos = [value.lat, value.lon]
    if (markerRef.current) {
      markerRef.current.setLatLng(pos)
    } else {
      markerRef.current = L.circleMarker(pos, {
        radius: 10, color: '#fff', weight: 2, fillColor: REPORT_COLOR, fillOpacity: 1,
      }).addTo(map)
      map.setView(pos, 16)
      return
    }
    if (!map.getBounds().pad(-0.2).contains(pos)) map.panTo(pos)
  }, [value])

  return (
    <div
      ref={containerRef}
      role="application"
      aria-label="Map: tap to place the light's location"
      style={{ height: 240, width: '100%', borderRadius: 12 }}
    />
  )
}
