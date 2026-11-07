# Solver output (feature #2) — handoff to B and C

Owner: Person A. Code: `backend/app/solver.py`. This is **not** the final result schema (`result-schema.json` is still to be agreed by all four). It is the raw material B's matching/scoring turns into that schema.

`solver.solve(image_path, lat, lon, taken_at, on_step, hints)` returns this dict, which `run_job` stores as the job's `result` (and `GET /api/measurements/{job_id}` serves).

```jsonc
{
  "solver_used": "local",            // "local" (solve-field) | "nova" (public API) | "stub" (tests)
  "wcs": {                           // astrometry.net's FITS header as a plain dict, incl. SIP terms
    "CTYPE1": "RA---TAN-SIP", "CRVAL1": 214.09, "CRPIX1": 1024.5, "CD1_1": -0.0186, "A_ORDER": 3, "A_0_2": -4.0e-06, ...
  },
  "sources": [ { "x": 1762.6, "y": 22.9, "flux": 9120.0 }, ... ],   // detected stars, brightest first, max 1000
  "stats": {
    "image_width_px": 2048, "image_height_px": 1509,
    "stars_detected": 2000,          // sources found (capped at 2000 by --objs; most are faint/noise)
    "stars_matched": 94,             // detections matched to catalog stars by the solver
    "log_odds": 485.5,               // local solver only: match confidence (we require >= 30)
    "field_width_deg": 62.78, "field_height_deg": 48.7,
    "ra_center": 214.0871, "dec_center": 62.5752, "pixel_scale_arcsec": 123.94,
    "solve_seconds": 16.44
  }
}
```

## Pixel convention (checked on real photos)
- `sources[].x/y` are **image pixels**: origin top-left, x right, y down, first pixel centre = (0, 0).
- The `wcs` accepts image pixels **directly** with astropy's `origin=0`, no flip, no shift:
  ```python
  from astropy.io import fits; from astropy.wcs import WCS
  wcs = WCS(fits.Header(result["wcs"]))
  x, y = wcs.all_world2pix(ra_deg, dec_deg, 0)      # sky -> image pixels (SIP distortion included)
  ra, dec = wcs.all_pix2world(x, y, 0)              # image pixels -> sky
  ```
- Why no flip: astrometry.net numbers JPEG/PNG pixels from 1 with y pointing down (like the image). I first assumed the usual FITS y-flip and the real-photo check caught it: the brightest detected stars sit on bright pixels only without a flip. `tests/test_solver_integration.py` keeps that check, plus a Big Dipper known-answer test (all seven stars project onto detected stars within 10 px).
- Rebuilding the WCS in your own code: use the **returned `wcs` dict**; don't refit. It already includes the SIP (order 3) lens-distortion terms.
- Typical accuracy on the two test photos: median ≈ 1–2 px between catalog stars and detections, worst ≈ 10–15 px at the edges. Night-mode photos may be worse (see CLAUDE.md §4).

## `sources` caveats for matching/scoring (B)
- The list is the brightest 1000 of up to 2000 detections. Photos with bright sky or foreground produce thousands of noise detections, so **a detection near a catalog star is weak evidence**; match radius and a flux sanity check are yours to tune.
- `flux` is relative, in image units, not magnitudes.

## Job `step` values (C)
`queued` (set by the upload route) → `detecting` → `solving`. B's stages add `matching` and `scoring`. Matches the keys in `Processing.jsx`.

## Failure `error` codes
All set `error.message` and `error.next_step` (plain text, show them as is) and `error.detected_stars` when known.

| code | when | typical next step |
|---|---|---|
| `too_few_stars` | fewer than 12 detections, found in ~2–6 s | take a Night-mode photo; may still add to the map (low confidence) |
| `no_match` | search finished, or fewer than 8 matched stars / low log-odds | cloud, blur, mostly foreground |
| `solve_timeout` | local 90 s limit or API 240 s limit | try again / more stars |
| `solver_unavailable` | no `solve-field` and no usable API key | try again later / sample photo |
| `solve_failed` | API or network error | try again |

## Settings (env vars, see `backend/.env.example`)
`SOLVER_MODE` = `auto` (default) | `local` | `api` | `stub`. In `auto`, the public API is used only when the local solver is missing or crashes; a local run that finishes with "no match" fails fast instead of waiting minutes on the API.
`LOCAL_SOLVE_TIMEOUT_S` (90), `API_SOLVE_TIMEOUT_S` (240), `ASTROMETRY_API_KEY`, `ASTROMETRY_INDEX_DIR`, `ASTROMETRY_CONFIG`.

## Measured on two openly licensed Commons photos (Docker Desktop on a dev laptop)
| photo | size | solve time | matched stars | field |
|---|---|---|---|---|
| Big Dipper over Great Sand Dunes (NPS, public domain) | 2048×1509 | 16 s | 94 | 62.8°×48.7° |
| Big Dipper over Sandvik (CC0) | 1536×2048 | 24 s | 126 | 45.8°×59.4° |

A third photo (a re-processed Flickr image of the Big Dipper) did **not** solve within 75 s, which is the "no match" path working as designed. Star extraction (6–18 s) dominates because these photos have 7–10k noise detections.
