// Colors shared by MapView and the Map page legend. Owner: Person D (#8).
// Bortle-style: 1 = darkest sky, 9 = most light-polluted.
export function scoreColor(score) {
  if (score == null) return '#9e9e9e' // failed solve: too few stars to score
  if (score <= 3) return '#43a047'
  if (score <= 6) return '#fbc02d'
  return '#e53935'
}

export const REPORT_COLOR = '#ab47bc'
