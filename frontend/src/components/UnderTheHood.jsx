// Person C (#13). Stats shown when the under-the-hood toggle is on. Numbers come from Person B.
const fmt = (v, digits = 0, suffix = '') => (v == null ? '—' : `${Number(v).toFixed(digits)}${suffix}`)
const SOLVERS = { local: 'Local astrometry.net', api: 'nova.astrometry.net API' }

export default function UnderTheHood({ stats }) {
  if (!stats) return null
  return (
    <section className="card hood-card" aria-label="Under the hood">
      <h2>Under the hood</h2>
      <p className="legend">
        <span className="key key-source" /> stars the solver found in your photo
        <br />
        <span className="key key-catalog">×</span> catalog stars we projected onto it
      </p>
      <dl className="facts facts-grid">
        <div><dt>Stars detected</dt><dd>{fmt(stats.stars_detected)}</dd></div>
        <div><dt>Matched to catalog</dt><dd>{fmt(stats.stars_matched)}</dd></div>
        <div><dt>Catalog stars in frame</dt><dd>{fmt(stats.catalog_in_frame)}</dd></div>
        <div><dt>Field of view</dt><dd>{fmt(stats.field_width_deg, 1)}° × {fmt(stats.field_height_deg, 1)}°</dd></div>
        <div><dt>Solve time</dt><dd>{fmt(stats.solve_seconds, 1, ' s')}</dd></div>
        <div><dt>Solver</dt><dd>{SOLVERS[stats.solver_used] ?? stats.solver_used ?? '—'}</dd></div>
      </dl>
    </section>
  )
}
