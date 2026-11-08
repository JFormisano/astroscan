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
`queued` (set by the upload route) → `detecting` → `solving` → `matching` (the pipeline step below). `scoring` will be added when B's scoring exists. Matches the keys in `Processing.jsx`.

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
`LOCAL_SOLVE_TIMEOUT_S` (90, shared across the field-size windows below), `API_SOLVE_TIMEOUT_S` (240), `ASTROMETRY_API_KEY`, `ASTROMETRY_INDEX_DIR`, `ASTROMETRY_CONFIG`.

## Measured on two openly licensed Commons photos (Docker Desktop on a dev laptop)
These are the solver alone on files that were already resized. **Through the real app the Sand Dunes photo takes 40–42 s** (the upload re-encodes the JPEG once more, and the added compression noise slows the engine step), so quote the end-to-end number.
| photo | size | solve time | matched stars | field |
|---|---|---|---|---|
| Big Dipper over Great Sand Dunes (NPS, public domain) | 2048×1509 | 16 s | 94 | 62.8°×48.7° |
| Big Dipper over Sandvik (CC0) | 1536×2048 | 24 s | 126 | 45.8°×59.4° |

A third photo (a re-processed Flickr image of the Big Dipper) did **not** solve within the 75 s CPU limit used in that early test; today that is reported as `solve_timeout` (or `no_match` if the search finishes without a match). Star extraction (6–18 s) dominates because these photos have 7–10k noise detections.

## Field-size windows (no camera data)
With a usable EXIF focal length the local solver searches one window around it (0.35x-1.2x of the estimate). Without one (chat apps and screenshots strip EXIF) it tries 30-80 degrees (phone main camera), then 10-30 (zoomed or cropped), then 80-120 (ultra-wide), extracting stars once and re-running only the matcher with a new scale. A real portrait phone photo with no EXIF solved in 20 s end to end this way (53 stars matched, 55.1 x 69.9 degree field); the old single 10-100 degree search timed out at 90 s on the same photo. Telescope or deep-sky images (about 1 degree wide) are outside every window and will end as `solve_timeout`.

## What the finished job `result` contains (after `app/pipeline.py`)
`run_job` passes the solver block through `pipeline.analyze()`, which keeps everything above and adds (the demo-cache shape the results page reads):

| Field | From | Notes |
|---|---|---|
| `image` | the job | `{url, width, height}`; `url` is the stored EXIF-stripped copy |
| `taken_at_utc`, `location` | the job | `location` is the ~1 km rounded `{lat, lon}` |
| `stars` | B's `match_stars` | every catalog star (mag <= 7) inside the frame: `{id, hip, name, mag, x, y, detected}`; `detected: false` = ghost star |
| `constellations` | B's `match_stars` | `{name, label, lines}` in image pixels |
| `conditions` | B's `evaluate_conditions` | Sun/Moon altitude, Moon illumination, field-centre altitude, `flags` |
| `warnings` | `conditions.flags` | `[{type: twilight\|moon\|low_altitude, moon_illumination_pct?}]`, a rename only |
| `planets` | B's `evaluate_conditions` + WCS | only planets above the horizon AND inside the photo: `{name, x, y, mag, alt_deg}` |
| `stats` | both | solver stats plus matching stats. **`stars_matched` is matching's number** (catalog stars with a detection next to them, what the page calls "Matched to catalog"); the solver's own count is `solver_stars_matched` |
| `score` | (B, not yet) | absent until `scoring.py` exists. Nothing invents a score |

If matching or the condition checks raise, the problem is logged and the job still ends `solved` with whatever was built (always at least the solver block plus `image`, `taken_at_utc`, `location`). A stub or WCS-less result passes through unchanged. For B: `pipeline.py` imports `matching._load_wcs`, `_near_field` and `_sky_to_image` (underscore names) for the planet projection; a public helper would be cleaner.

Check on a real photo: the Big Dipper's seven stars come out of the pipeline named, at the WCS-projected pixel, with a detection on top (`tests/test_solver_integration.py`).
