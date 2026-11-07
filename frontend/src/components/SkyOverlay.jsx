// Person C (#5, #13). Draws the backend's results on top of the photo.
// One SVG whose viewBox is the image's pixel size, so every coordinate from the backend
// (image pixels, origin top-left, x right, y down) is used as-is at any screen size.
// The frontend does no astronomy math; it only draws what it's given.

// Dot radius in image units for a star of a given magnitude (brighter = bigger).
const starRadius = (mag, unit) => Math.max(1.4, 5.2 - 0.65 * mag) * unit

export default function SkyOverlay({ result, showLabels, showGhosts, showHood }) {
  const { width: w, height: h, url } = result.image
  const unit = Math.max(w, h) / 1000 // ~1 unit per 1000 px of the long side
  const stars = result.stars ?? []
  const ghosts = stars.filter((s) => !s.detected)
  const named = stars.filter((s) => s.detected && s.name)
  const text = { fontSize: 15 * unit, strokeWidth: 3 * unit }

  return (
    <svg
      className="sky"
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label={`Your sky photo with ${named.length} named stars${showGhosts ? ` and ${ghosts.length} hidden stars` : ''} marked`}
    >
      <defs>
        <radialGradient id="ghost-glow">
          <stop offset="0%" stopColor="#dfe9ff" stopOpacity="1" />
          <stop offset="35%" stopColor="#9fc0ff" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#6f9cff" stopOpacity="0" />
        </radialGradient>
      </defs>

      {url ? (
        <image href={url} width={w} height={h} />
      ) : (
        // No image (dev fake): dark sky with the detected stars as dots.
        <g>
          <rect width={w} height={h} fill="#05070f" />
          {stars.filter((s) => s.detected).map((s) => (
            <circle key={s.id} cx={s.x} cy={s.y} r={starRadius(s.mag, unit) * 0.8} fill="#fff" />
          ))}
        </g>
      )}

      {showGhosts && (
        <g className="ghosts">
          {ghosts.map((s) => (
            <circle key={s.id} cx={s.x} cy={s.y} r={starRadius(s.mag, unit) * 2.6} fill="url(#ghost-glow)" />
          ))}
        </g>
      )}

      {showLabels && (
        <g className="labels">
          {(result.constellations ?? []).map((c) => (
            <g key={c.name}>
              {c.lines.map(([x1, y1, x2, y2], i) => (
                <line
                  key={i}
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#8fb4ff" strokeOpacity="0.65" strokeWidth={1.6 * unit} strokeLinecap="round"
                />
              ))}
              {c.label && (
                <text x={c.label.x} y={c.label.y} className="sky-text constellation" style={{ ...text, fontSize: 19 * unit }}>
                  {c.name}
                </text>
              )}
            </g>
          ))}
          {named.map((s) => (
            <g key={s.id}>
              <circle cx={s.x} cy={s.y} r={9 * unit} fill="none" stroke="#fff" strokeOpacity="0.8" strokeWidth={1.2 * unit} />
              <text x={s.x + 12 * unit} y={s.y + 5 * unit} className="sky-text" style={text}>{s.name}</text>
            </g>
          ))}
          {(result.planets ?? []).map((p) => (
            <g key={p.name}>
              <rect
                x={p.x - 7 * unit} y={p.y - 7 * unit} width={14 * unit} height={14 * unit}
                transform={`rotate(45 ${p.x} ${p.y})`}
                fill="none" stroke="#ffc46b" strokeWidth={1.8 * unit}
              />
              <text x={p.x + 13 * unit} y={p.y + 5 * unit} className="sky-text planet" style={text}>{p.name}</text>
            </g>
          ))}
        </g>
      )}

      {showHood && (
        <g className="hood">
          {/* Circles: what the solver detected in the photo. */}
          {(result.sources ?? []).map((s, i) => (
            <circle key={i} cx={s.x} cy={s.y} r={6 * unit} fill="none" stroke="#5ef08f" strokeWidth={1.2 * unit} />
          ))}
          {/* Crosses: catalog stars we projected into the photo. */}
          {stars.map((s) => {
            const a = 4 * unit
            return (
              <path
                key={s.id}
                d={`M${s.x - a} ${s.y - a}L${s.x + a} ${s.y + a}M${s.x - a} ${s.y + a}L${s.x + a} ${s.y - a}`}
                stroke="#ff9d4d" strokeWidth={1.2 * unit}
              />
            )
          })}
        </g>
      )}
    </svg>
  )
}
