// Constellations inside the landing telescope.
// Tap one to pick it out. Tap it again, or tap AstroScan, to zoom into the title.
import { useState } from 'react'

const FIGURES = [
  {
    id: 'orion',
    name: 'Orion',
    x: 24,
    y: 26,
    stars: [[50, 8], [22, 28], [78, 30], [38, 48], [50, 50], [62, 52], [30, 86], [76, 84]],
    lines: [[0, 1], [0, 2], [1, 3], [2, 5], [3, 4], [4, 5], [3, 6], [5, 7]],
  },
  {
    id: 'dipper',
    name: 'Big Dipper',
    x: 72,
    y: 22,
    stars: [[12, 58], [30, 40], [52, 36], [70, 54], [78, 34], [90, 16], [98, 4]],
    lines: [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6]],
  },
  {
    id: 'cassiopeia',
    name: 'Cassiopeia',
    x: 68,
    y: 76,
    stars: [[6, 62], [28, 16], [50, 58], [72, 14], [94, 48]],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4]],
  },
  {
    id: 'cygnus',
    name: 'Cygnus',
    x: 24,
    y: 74,
    stars: [[50, 6], [50, 34], [50, 62], [50, 92], [14, 46], [86, 40]],
    lines: [[0, 1], [1, 2], [2, 3], [4, 1], [1, 5]],
  },
]

function Figure({ stars, lines }) {
  return (
    <svg viewBox="0 0 100 100" aria-hidden="true">
      {lines.map(([a, b], i) => (
        <line key={i} x1={stars[a][0]} y1={stars[a][1]} x2={stars[b][0]} y2={stars[b][1]} />
      ))}
      {stars.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 0 ? 3.1 : 2.15} />
      ))}
    </svg>
  )
}

export default function Eyepiece({ onEnter, onSkip, onLook }) {
  const [activeId, setActiveId] = useState(null)
  const active = FIGURES.find((figure) => figure.id === activeId) ?? null

  function choose(id) {
    if (id === activeId) onEnter()
    else {
      setActiveId(id)
      onLook?.()
    }
  }

  return (
    <>
      <div className={active ? 'scope-stage is-focused' : 'scope-stage'}>
        {FIGURES.map((figure) => (
          <button
            key={figure.id}
            type="button"
            className={figure.id === activeId ? 'constellation is-active' : 'constellation'}
            style={{ left: `${figure.x}%`, top: `${figure.y}%` }}
            aria-pressed={figure.id === activeId}
            onClick={() => choose(figure.id)}
          >
            <Figure stars={figure.stars} lines={figure.lines} />
            <span>{figure.name}</span>
          </button>
        ))}
        <button type="button" className="scope-title" onClick={onEnter}>
          AstroScan
          <small>{active ? active.name : 'Zoom in'}</small>
        </button>
      </div>
      <p className="scope-note" aria-live="polite">
        {active ? `Tap ${active.name} again to zoom in` : 'Tap a constellation'}
      </p>
      <button type="button" className="skip-chip" onClick={onSkip}>
        Skip
      </button>
    </>
  )
}
