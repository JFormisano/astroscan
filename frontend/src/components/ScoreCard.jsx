// Person C (#4 display). 1 = darkest, 9 = most light-polluted (Bortle-style, not Bortle).
// Numbers come from Person B's scoring.py; this only words them.
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

// scoring.py confidence_reasons → plain words. The catalog-limit reason is currently sent as
// a sentence rather than a code, so both forms are listed.
const CATALOG_LIMIT = 'Your sky may be even darker than we can measure (our star catalog stops at magnitude 7)'
const REASONS = {
  twilight: "The sky wasn't fully dark yet (twilight)",
  moon_up: 'The Moon was up',
  low_altitude: 'The photo points close to the horizon',
  few_matched_stars: 'Only a few stars could be matched',
  missing_exif: "Your photo doesn't include its camera settings, so we couldn't check them",
  exposure_out_of_range: 'The exposure time is outside the range our score is tuned for',
  iso_out_of_range: 'The ISO is outside the range our score is tuned for',
  catalog_limit: CATALOG_LIMIT,
  'sky darker than the catalog can measure': CATALOG_LIMIT,
}
const reasonText = (r) => REASONS[r] ?? (/^[a-z_]+$/.test(r) ? r.replaceAll('_', ' ') : r)

export default function ScoreCard({ score }) {
  const value = Math.min(9, Math.max(1, Math.round(score.value)))
  // The catalog ends at mag 7, so the darkest score it can give is a floor, not an exact class.
  const floor = score.limiting_mag_is_lower_bound === true
  const reasons = Array.isArray(score.confidence_reasons) ? [...new Set(score.confidence_reasons.map(reasonText))] : []
  return (
    <section className="card score-card" aria-label="Sky quality score">
      <div className="score-top">
        <div className={`score-num s${value}`}>
          {value}
          <span>/9</span>
        </div>
        <div>
          <div className="score-label">
            {LABELS[value]}
            {floor && ' or darker'}
          </div>
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
            <dd>
              mag {score.limiting_mag.toFixed(1)}
              {floor && <span className="dd-note"> or fainter</span>}
            </dd>
          </div>
        )}
      </dl>
      {reasons.length > 0 && (
        <div className="reasons">
          <p className="small">Why we&apos;re less sure:</p>
          <ul className="small muted">
            {reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      )}
      <p className="muted small">
        Your sky as your phone saw it. This is an estimate, calibrated from published naked-eye limits; your
        camera&apos;s settings affect it too.
      </p>
    </section>
  )
}
