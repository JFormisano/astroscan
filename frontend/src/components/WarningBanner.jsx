// Person C (#7 display). Person B produces the flags; this only words and shows them.
function text(w) {
  switch (w.type) {
    case 'twilight':
      return "The sky wasn't fully dark yet (twilight), so your score reads brighter than your real night sky."
    case 'moon':
      return `The Moon was up${w.moon_illumination_pct != null ? ` (${Math.round(w.moon_illumination_pct)}% lit)` : ''}. Moonlight hides faint stars, so a moonless night would likely score better.`
    case 'low_altitude':
      return 'You were pointing close to the horizon, where haze and city glow are strongest. Aim higher for a fairer reading.'
    default:
      return w.message ?? null
  }
}

export default function WarningBanner({ warnings }) {
  const items = (warnings ?? []).map((w) => ({ key: w.type, msg: text(w) })).filter((w) => w.msg)
  if (!items.length) return null
  return (
    <div className="warnings" role="status">
      {items.map((w) => (
        <p key={w.key} className="alert alert-warn">
          <strong>Heads up:</strong> {w.msg}
        </p>
      ))}
    </div>
  )
}
