// Person C (#4 display). 1 = darkest, 9 = most light-polluted (Bortle-style, not Bortle).
const LABELS = {
  1: 'Pristine dark sky',
  2: 'Truly dark sky',
  3: 'Rural sky',
  4: 'Rural / suburban edge',
  5: 'Suburban sky',
  6: 'Bright suburban sky',
  7: 'Suburban / city edge',
  8: 'City sky',
  9: 'Inner-city sky',
}
const CONFIDENCE = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence: treat as a rough guess',
}

export default function ScoreCard({ score }) {
  const value = Math.min(9, Math.max(1, Math.round(score.value)))
  return (
    <section className="card score-card" aria-label="Sky quality score">
      <div className="score-top">
        <div className={`score-num s${value}`}>
          {value}
          <span>/9</span>
        </div>
        <div>
          <div className="score-label">{LABELS[value]}</div>
          <div className="muted small">Bortle-style scale: 1 darkest, 9 brightest</div>
          <span className={`badge badge-${score.confidence}`}>{CONFIDENCE[score.confidence] ?? score.confidence}</span>
        </div>
      </div>
      <div className="scale" aria-hidden="true">
        {Array.from({ length: 9 }, (_, i) => (
          <span key={i} className={`seg s${i + 1}${i + 1 === value ? ' on' : ''}`} />
        ))}
      </div>
      <dl className="facts">
        {typeof score.pct_lost === 'number' && (
          <div>
            <dt>Stars lost to light</dt>
            <dd>{Math.round(score.pct_lost)}%</dd>
          </div>
        )}
        {typeof score.limiting_mag === 'number' && (
          <div>
            <dt>Faintest stars seen</dt>
            <dd>mag {score.limiting_mag.toFixed(1)}</dd>
          </div>
        )}
      </dl>
      <p className="muted small">
        Your sky as your phone saw it. This is an estimate, calibrated from our own photos; your camera&apos;s
        settings affect it too.
      </p>
    </section>
  )
}
