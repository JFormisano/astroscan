// Person C (#13). Stats shown when the under-the-hood toggle is on. Numbers come from the
// solver (Person A) and matching (Person B); rows without a value are left out.
const SOLVERS = {
  local: 'Local astrometry.net',
  nova: 'nova.astrometry.net API',
  api: 'nova.astrometry.net API',
  stub: 'Test stub (no real solve)',
}
const num = (v, digits = 0) => (v == null || Number.isNaN(Number(v)) ? null : Number(v).toFixed(digits))

export default function UnderTheHood({ stats, showCatalogKey = true }) {
  const s = stats ?? {}
  const fw = num(s.field_width_deg, 1)
  const fh = num(s.field_height_deg, 1)
  const solveTime = num(s.solve_seconds, 1)
  const rows = [
    ['Stars detected', num(s.stars_detected)],
    ['Matched to catalog', num(s.stars_matched)],
    ['Catalog stars in frame', num(s.catalog_in_frame)],
    ['Field of view', fw && fh ? `${fw}° × ${fh}°` : null],
    ['Solve time', solveTime && `${solveTime} s`],
    ['Solver', s.solver_used ? (SOLVERS[s.solver_used] ?? s.solver_used) : null],
  ].filter(([, v]) => v != null)

  return (
    <section className="card hood-card" aria-label="Under the hood">
      <h2>Under the hood</h2>
      <p className="legend">
        <span className="key key-source" /> stars the solver found in your photo
        {showCatalogKey && (
          <>
            <br />
            <span className="key key-catalog">×</span> catalog stars we projected onto it
          </>
        )}
      </p>
      {rows.length > 0 && (
        <dl className="facts facts-grid">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
