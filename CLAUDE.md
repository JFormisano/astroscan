# CLAUDE.md — UB Hacking: Light Pollution Sky App

> Read this whole file at the start of every session. It is the source of truth for scope, architecture and conventions. If a request conflicts with this file, point out the conflict before writing code.

Working name: **TBD — pick by hour 2** (needed for the domain, Devpost and pitch; judges remember names)
Event: UB Hacking (24 hours) — team of 4
Team: Person A (photo in, solve out) · Person B (astronomy math) · Person C (main user flow) · Person D (map, reports, AI, demo) — *fill in names*. Full split in §2 "Who builds what".
Pitch: the whole team works on it together after the hour-18 feature freeze.

**Status (Nov 7, from git history and the last test runs):**
- Merged to `main`: #1 upload backend (A), #1 upload/processing frontend + #5/#7/#12/#13 screens built on fake data (C), #8 map route and page (D).
- **#2 plate solving (A): done on branch `jacob-#2_Plate_Solving`, not yet merged.** Local `solve-field` in Docker is primary, the public nova API is the fallback, both tested on real photos. Output shape and pixel convention: `docs/solver-output.md`.
- Still open: `docs/result-schema.json` (not agreed yet), B's matching/scoring/conditions (modules are empty stubs), #9–#11 (D; `ai.py`, `demo.py`, `light_reports.py` are stubs and `demo_cache/` is empty), deploy, Night-mode photo tests.

---

## 1. What we're building

A free, mobile-first **website** where anyone uploads a photo of the night sky and gets:

1. **Identify** — constellations, named stars and planets drawn on their photo
2. **Measure** — a 1–9 sky quality score for that place and time
3. **Show** — "ghost stars": the stars light pollution is hiding, overlaid on their photo
4. **Collect** — their result added to a shared light pollution map
5. **Act** — a "light report": photograph a problem light, pin it, get an AI-drafted request to whoever controls it

### The problem (for context and the pitch)
- The night sky got ~10% brighter per year from 2011–2022 (Kyba et al., *Science*, 2023, from Globe at Night data).
- Satellites measured only ~2%/yr, partly because they miss blue LED light and sideways-emitted light. Ground-level measurements fill that gap.
- Existing tools: Dark Sky Meter (mostly iPhone, gives a number), Globe at Night / Loss of the Night (manual star counting), and **Asterism** (asterism.quietlife.net, launched Aug 2026), which already labels stars, constellations and planets on phone photos. Asterism has no sky score, map or light reports — that's our ground.
- **Our angle:** "Dark Sky Meter gives you a number. We show you what you're missing" — on any phone, in the browser, from a photo.

### Who it's for
- **Stargazers and students** who want to know what they're looking at and how bright their sky is.
- **Local advocates (including UB itself)** who need ground-level evidence and an easy way to ask for a fix.
- Every feature and every pitch line should serve one of these two people. Star identification alone is common (SkyView, Stellarium); **ghost stars + the map + light reports** are what make this different, so lead with them.

---

## 2. Scope

### Build (in this order)
Every feature has a priority. **Must** features are the demo: without them there is no project. **Should** features make it strong. **Could** features are the first to cut if a checkpoint in §7 is missed.

- **Must:** #1, #2, #3, #4, #5, #11, #12 — upload → solve → labels, ghost stars and score on screen, plus demo mode and a clear failure message
- **Should:** #6, #7, #8, #13 — planets, warnings, map, under-the-hood view
- **Could:** #9, #10 — light reports and the AI explainer (cut light reports to plain map pins first)

| # | Feature | Simplification that makes it fit in 24h |
|---|---|---|
| 1 | Upload flow | Photo upload, read EXIF time, browser geolocation, confirm screen. Processing page shows clear steps ("finding stars… matching…") and the result has its own URL (`/results/{job_id}`) so a refresh or locked phone doesn't lose it |
| 2 | Plate solving backend | Public astrometry.net API first (works today, unblocks everyone), then local `solve-field` with wide-field index files as the primary once it runs (see §4); simple polling (no real job queue) |
| 3 | Star matching | Use the solver's outputs (WCS + extracted sources); no custom star detector |
| 4 | Sky score | Limiting magnitude → 1–9 rating + "% of stars lost". No sky-background photometry |
| 5 | Results page + ghost stars | Constellation lines, labels, ghost-star toggle. **Demo centerpiece** |
| 6 | Planets | Computed from photo timestamp + location |
| 7 | Twilight / Moon / low-altitude warnings | Sun and Moon positions; field-center altitude |
| 8 | Map | Leaflet + Supabase; locations rounded to ~1 km |
| 9 | Light reports | Photo + pin + AI-drafted message with a Copy button. **Never send email** |
| 10 | AI explainer | One API call using the score and solved results |
| 11 | Demo mode | Cached results (including cached AI text) from pre-solved photos. **"Try a sample photo" button on the landing page** so judges without a night photo can use the app on their own phone |
| 12 | Failed-solve message | "Too few stars to identify" + basic detected-star count |
| 13 | "Under the hood" toggle | On the results page: circles = stars the solver found, crosses = catalog stars we projected, plus stats (stars matched, field size, solve time). Cheap, and it shows judges the real technical work |

### Who builds what
Development work is split evenly by feature. Each person owns their features from backend to screen. After the hour-18 feature freeze, all four work on the pitch, Devpost and demo video together.

| Person | Features (numbers from the table above) | Files they own |
|---|---|---|
| **A — photo in, solve out** | **#1 Upload flow (backend):** upload route, reading EXIF time and camera settings, EXIF stripping, size limits · **#2 Plate solving:** local `solve-field` in Docker, public API fallback, job status and polling · repo setup, Supabase, deploys, keep-alive | `app/main.py`, `app/routes/measurements.py`, `app/solver.py`, `app/db.py`, `Dockerfile` |
| **B — astronomy math** | **#3 Star matching** · **#4 Sky score** (incl. the calibration table) · **#6 Planets** · **#7 Warnings (the math)** · all known-answer math tests · the numbers shown in the under-the-hood view | `app/matching.py`, `app/scoring.py`, `app/conditions.py`, `data/`, `tests/` for math |
| **C — main user flow** | **#1 Upload flow (frontend):** upload page, geolocation, confirm screen, processing page · **#5 Results page + ghost stars** · **#7 Warning banners (the display)** · **#12 Failed-solve message** · **#13 Under-the-hood toggle** · mobile layout on iPhone and Android | `pages/Upload`, `pages/Processing`, `pages/Results`, `SkyOverlay`, `ScoreCard`, `WarningBanner`, `UnderTheHood` |
| **D — map, reports, AI, demo** | **#8 Map** (route + page) · **#9 Light reports** end to end · **#10 AI explainer** · **#11 Demo mode** (cache, "Try a sample photo" button) · the test photo set | `app/ai.py`, `app/routes/map.py`, `app/routes/light_reports.py`, `app/routes/demo.py`, `pages/Map`, `pages/LightReport`, `pages/Landing`, `MapView`, `demo_cache/` |

**Why this is even:** A's list looks shortest, but #2 is the hardest feature in the project and A also carries setup and deploys. #1 and #7 are split on purpose: the backend owner produces the data and C builds the screen for it.

**Shared files:** `frontend/src/api.js` and the result JSON schema (`/docs/result-schema.json`) are shared. Add your own functions to `api.js` without changing anyone else's. Any change to the result schema is agreed by all four first, because B produces it, C and D draw it and the demo cache stores it.

**Handoffs:**
- **Hour 0–1 (all four):** agree on the result JSON shape, write it to `/docs/result-schema.json` and hand-make one fake result in `demo_cache/`. Everyone builds against this fake result until real solves work, so nobody waits on the solver.
- **Hour 2:** A's deployed backend returns the fake result; C and D switch from the local file to real API calls.
- **Hour 8:** A's solver output → B's matching and scoring → C's results page. First real photo on screen. A's solver output is available now as the "raw solver block" in `docs/solver-output.md` (WCS + detected stars + stats); it is input for B, **not** the final result schema.
- **After the solver works (~hour 8–10):** A helps C with the frontend.
- **After scoring works (~hour 14):** B helps D, starting with filling the demo cache from real solves.
- **Hour 18:** feature freeze. Everyone switches to bug fixes, phone testing and the pitch.

### Stretch (only if ahead at hour 16)
Live AR ghost view (camera + device sensors, tap-to-align) · video upload (sharpest frame) · AI photo check (clouds / non-sky) · "Where were you pointing?" picker for failed solves

### Out of scope — do not build
User accounts · shareable report card · satellite data comparison · tonight's conditions panel · red mode · CSV export · before/after re-measuring · in-browser photo capture (browsers can't do long exposures; users shoot with their phone's Night mode and upload)

---

## 3. Architecture

```
Phone browser (React)
   │  upload image + lat/lon + taken_at
   ▼
Backend (Python / FastAPI, Docker)
   ├─ solver.py           → local solve-field (fallback: astrometry.net API) → WCS + extracted stars
   ├─ matching.py         → project catalog stars into image, mark detected / missing
   ├─ scoring.py          → limiting magnitude, 1–9 score, % lost, confidence
   ├─ conditions.py       → Sun / Moon / altitude flags, planet positions
   ├─ ai.py               → Claude API: explainer + light-report drafts
   └─ db.py               → Supabase (Postgres + storage, incl. job status)
   │
   ▼  JSON result (all overlay coordinates in image pixels)
Frontend renders overlays on the photo (SVG or canvas)
```

**Key principle:** all astronomy math lives in the backend. The frontend only draws what the backend returns. (Exception: the stretch AR view, which needs math in the browser.)

### Stack
- **Frontend:** React + Vite, mobile-first. Leaflet + OpenStreetMap tiles for the map.
- **Backend:** Python + FastAPI in a Docker image that includes astrometry.net's `solve-field` (Debian package, v0.97) and only the wide-field index files (4110–4119, about 46 MB, downloaded and checksum-verified at build time). `astropy` (WCS projection), `numpy`, `Pillow` (EXIF), `astronomy-engine` (Sun/Moon/planets).
- **Database / storage:** Supabase.
- **AI:** Anthropic API, called **only from the backend**. Check docs.claude.com for current model names.
- **Hosting:** Vercel free tier (frontend). Backend on a host with real CPU. HTTPS is required.
  - `solve-field` is CPU-bound. Render's free tier gives 0.1 CPU and 512 MB RAM and spins down after 15 minutes idle (about a minute to wake), so a solve there would be far too slow. Use a paid instance with at least 0.5–1 CPU for the weekend (Render Starter is $7/month with 0.5 CPU and no spin-down), or sponsor cloud credits if the event offers them.
  - Run **one worker** and one solve at a time; parallel solves on a small machine just make every solve slower. The solver enforces this with a lock around the local solve only; waiting jobs stay `pending`.
  - **Timing caveat:** the ~40 s end-to-end solve quoted in §4 was measured in Docker Desktop on a many-core dev laptop. `astrometry-engine` is single-threaded, so a 0.5-CPU host will be roughly 2x slower or worse and could hit the 90 s default limit. `render.yaml` therefore asks for 1 CPU / 2 GB and `LOCAL_SOLVE_TIMEOUT_S=120`. Container memory peaked at about 290 MiB (including file cache). Re-measure on the deployed instance before the pitch (`backend/scripts/smoke.py`). Run/deploy guide: `docs/deploy.md`.
  - **The backend must not sleep during judging.** Use an always-on instance; keep `/api/health` for a quick check.
  - **Run and deploy:** `docker compose up --build` runs the whole app on one PC (http://localhost:8080); `docker-compose.prod.yml` + `deploy/Caddyfile` put the same stack on ONE server with automatic HTTPS and the real solver (tested end to end with `DOMAIN=localhost`); `render.yaml`, `frontend/vercel.json` and `docs/deploy.md` cover the Render + Vercel + Supabase alternative. `backend/scripts/smoke.py <url> <photo> --require-local` is the post-deploy check (health time = cold start, a full solve, and it fails unless the server really uses `solve-field`).

### Proposed layout
```
/frontend
  src/pages/        Landing, Upload, Processing, Results, Map, LightReport
  src/components/   SkyOverlay, ScoreCard, WarningBanner, MapView, UnderTheHood
  src/api.js        all backend calls in one place
/backend
  Dockerfile        includes solve-field + wide-field index files (build downloads ~46 MB)
  app/main.py       app setup; includes the routers below (A)
  app/routes/       measurements.py (A) · map.py, light_reports.py, demo.py (D)
  app/solver.py     local solve-field + astrometry.net API fallback (A, done)
  app/imaging.py    validate, read EXIF, strip EXIF, resize, round coordinates (A, done)
  app/errors.py     ApiError: code + plain message + next step (A)
  app/matching.py
  app/scoring.py
  app/conditions.py
  app/ai.py
  app/db.py
  data/             star catalog (filtered HYG), constellation lines JSON
  demo_cache/       pre-solved demo results (do not delete)
  tests/            test_solver.py (no solve-field needed) · test_solver_integration.py (Docker, real photos)
/docs               spec, pitch notes, judge Q&A, solver-output.md
/test_photos        openly licensed test photos, git-ignored (never commit)
```

### API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/measurements` | multipart image + lat, lon, optional taken_at / tz_offset_minutes (used when EXIF has no time) → `{ job_id }` |
| GET | `/api/measurements/{job_id}` | `{ job_id, status: pending\|solved\|failed, step, result, error, image_url, taken_at_utc, lat, lon, flags }`. `step` is `queued\|detecting\|solving` (then B's `matching\|scoring`). `error` is `{ code, message, next_step, detected_stars? }` |
| GET | `/api/measurements/{job_id}/image` | the EXIF-stripped photo (local storage only; Supabase serves its own URL) |
| GET | `/api/map` | measurements + light reports for the map |
| POST | `/api/light-reports` | photo + lat, lon, category, note → report + drafted message |
| GET | `/api/demo/{name}` | cached demo result, same shape as a real result |
| GET | `/api/health` | keep-alive ping and deploy check: `{ status, solver: { mode, using: local\|api\|stub\|none, local_available, index_files, api_key_set } }` (no secrets). `using` must be `local` in production |

### Data model (Supabase)
- **measurements:** id, created_at, status (pending|solved|failed), taken_at_utc, lat_rounded, lon_rounded, score, limiting_mag, pct_lost, confidence, flags (jsonb — includes exposure_s, iso, f_number, solve_seconds, solver_used), image_url (EXIF-stripped copy), solved (bool), is_demo (bool), plus `step` (text), `result` (jsonb, the solver block today) and `error` (jsonb) so polling can serve progress, results and failure messages. SQL: `backend/supabase/schema.sql`. Without Supabase credentials the backend uses `LocalStore` (JSON files under `backend/storage/`)
- **light_reports:** id, created_at, lat_rounded, lon_rounded, photo_url (EXIF-stripped copy), category, note, drafted_message, measurement_id (nullable)

---

## 4. How the core works

### Plate solving
**Status: built and tested (feature #2).** `solver.py` hides which solver ran, so nothing outside it changes between them. `SOLVER_MODE` (env): `auto` (default) | `local` | `api` | `stub`.

**Primary: astrometry.net locally.** `solve-field` in the backend's Docker image with the 4110–4119 wide-field index files (about 46 MB total; 4107–4109 are 310 MB and only fit telescope fields; `solve-field` skips indexes outside the scale range, so extras cost almost nothing). The solve runs in two stages, the same two `solve-field` runs internally, so we can look in between:
1. `solve-field --just-augment` extracts stars and writes an `.axy` file (2–18 s on a ≤2048 px photo). If fewer than 12 stars: stop with `too_few_stars` and the count, instead of searching until a timeout.
2. `astrometry-engine -c <cfg> photo.axy` matches star patterns and writes `.wcs`, `.corr`, `.match`, `.solved`.

Settings that came out of measuring on real photos:
- **Scale hint:** the photo's x-axis width from the EXIF 35 mm focal length (`2·atan(S/2f)`, S = 36 mm landscape / 24 mm portrait), searched at 0.35×–1.2× of that estimate (phone crops make EXIF wrong), clamped to 2–120°. **No EXIF** (chat apps and screenshots strip it, so this is common): try windows in turn, extracting stars only once and re-running just the engine with a new scale (`ANAPPL1`/`ANAPPU1`/`ANCLIM` in the `.axy`): 30–80° (phone main camera, portrait or landscape), then 10–30° (zoomed/cropped), then 80–120° (ultra-wide). One 10–100° search was about 10x slower: a real phone photo solved in 20 s end to end with the staged windows and timed out at 90 s with 10–100°. Telescope images (about 1° wide) are outside every window and are not supported.
- **Distortion:** `--tweak-order 3` (SIP) and `--crpix-center`. On two test photos, catalog stars land a median 1–2 px from detections, worst 10–15 px at the edges.
- **`--objs 2000`:** keeps the brightest 2000 detections. It cut the engine step from 12 s to 3–5 s with identical matches (photos with bright foreground yield 7–10k mostly-noise detections). Faint stars stay in because ghost-star detection needs them.
- **No `--downsample`:** `--downsample 2` was slower overall and halved the matches. The upload step already caps the photo at 2048 px on the long side.
- **Don't trust the exit code:** `solve-field` exits 0 even when it didn't solve. We accept a solve only if the `.solved` file exists **and** the `.corr` file has at least 8 matched stars **and** the `.match` log-odds is at least 30 (solve-field itself solves at about 20.7). Weak solves become `no_match`.
- **Time limit:** `LOCAL_SOLVE_TIMEOUT_S` (default 90) is the total for the engine step, split across the windows (55% for the first, the rest shared). Each window is limited by `--cpulimit` and a wall-clock kill of the whole process group; no solver processes are left behind. A window that is searched fully with no match moves on to the next; if any window ran out of time the failure is `solve_timeout`, otherwise `no_match`.

**Fallback: public nova.astrometry.net API** (`https://nova.astrometry.net`). Flow: `POST /api/login` with `request-json={"apikey": ...}` → `POST /api/upload` (multipart: `request-json` + `file`) → poll `/api/submissions/{id}` for a job id (the list holds `null` while queued) → poll `/api/jobs/{id}` until `success`/`failure` → download `/wcs_file/{job}`, `/axy_file/{job}`, `/corr_file/{job}`. Uploads are sent with `publicly_visible: "n"`, only the stripped photo, and no location or time. Login errors come back as HTTP 200 with `{"status": "error", "errormessage": ...}`.
- Measured Nov 7: a real photo solved in **41 s** with the key working (an earlier test the same day took about 10 minutes, so queue time varies a lot). Nova downsamples internally, so it finds fewer stars (430 detected, 49 matched vs 2000 / 94 locally) but the WCS agrees with the local one (same field size and pixel scale; Big Dipper stars within 3.4 px).
- Give-up time: `API_SOLVE_TIMEOUT_S` (default 240), under the frontend's 6-minute wait.

**When each is used (`auto`):** local if `solve-field`, `astrometry-engine` and index files are present; if local is missing or **crashes**, fall back to the API (needs `ASTROMETRY_API_KEY`, else `solver_unavailable`). A local run that **finishes** with `no_match`, `too_few_stars` or `solve_timeout` fails fast; it is **not** retried on the API, so a bad photo never turns into a multi-minute wait. `local` never calls the API; `api` never runs locally (this is how a Windows dev machine without Docker runs).

**What the solver returns** (`docs/solver-output.md`): `solver_used`, `wcs` (the FITS header, including SIP terms, as a dict), `sources` (detected stars, brightest first, max 1000, in image pixels) and `stats` (detected, matched, field size, centre, pixel scale, log-odds, solve seconds).

**Pixel convention (verified on real photos; I assumed a y-flip first and was wrong):** astrometry.net counts JPEG/PNG pixels from 1 with y pointing down, like the image. So `sources` are already image pixels (shifted by 1, no flip) and the returned WCS takes image pixels directly: `WCS(fits.Header(result["wcs"])).all_world2pix(ra, dec, 0)`. Do not flip y anywhere.

**Measured solves** (Docker Desktop on a many-core dev laptop, public-domain/CC0 Wikimedia Commons Big Dipper photos). The solver alone on an already-resized file: 2048×1509 in 16 s (94 matched, 62.8°×48.7° field) and 1536×2048 in 24 s (126 matched, 45.8°×59.4°). **Through the real app it is slower: the Sand Dunes photo takes 40–42 s end to end** (three runs), because the upload re-encodes the JPEG a second time and the extra compression noise made the engine step take 18–34 s instead of ~10 s. Use the end-to-end number in the pitch. (`--objs` 300–1000 only recovered about 20%, so it stayed at 2000 to keep faint stars for ghost-star detection.) a third, re-processed Flickr photo did not solve within the 75 s CPU limit of that early test (the app would now report it as `solve_timeout`, or `no_match` if the search had finished). Star extraction (6–18 s) is now the slowest part. Still untested: phone Night-mode photos (star-position shifts), and any host with a small CPU.

Either way we need: the **WCS solution** (maps sky coordinates ↔ image pixels), the **list of extracted sources** (detected stars in pixels) and optionally its **annotations** (not used). **Confirm exact flags, endpoints and output files against current astrometry.net docs or `solve-field --help`** — don't guess. (Flags confirmed in the Debian 0.97 build: `--just-augment`, `--axy`, `--objs`, `--tweak-order`, `--crpix-center`, `--cpulimit`, `--scale-units/low/high`, `--no-plots`, `--overwrite`, `--dir`, `--out`, `--config`.)

### Star matching
1. Load catalog stars (filtered HYG, roughly magnitude ≤ 7).
2. Project each into image pixels with the WCS (`astropy.wcs`), loading the full WCS header from `result["wcs"]` so the distortion (SIP) terms are applied, and call `all_world2pix(ra, dec, 0)` (origin 0, no flip; see §4 "Pixel convention"). Keep those inside the frame.
3. The solver's `sources` list holds up to 1000 detections, many of them noise on photos with bright sky or foreground, so a source near a catalog star is weak evidence on its own; use flux and a sensible radius. A catalog star is **detected** if an extracted source lies within N pixels (start with ~3–5 px; tune on our photos; may need a larger radius near the edges). **Phone Night mode stacks many frames and can shift stars by up to ~1° in parts of the image**, so test on Night mode photos early. If labels drift, snap each label to the nearest detected star within a larger radius rather than writing a full correction model.
4. Output per star: pixel x/y, name (if any), magnitude, detected (bool). Undetected stars = ghost stars.
5. Constellation lines: project line endpoints the same way.

### Scoring
- **Direction:** 1 = darkest, 9 = most light-polluted, the same direction as the Bortle scale. Call it "Bortle-style" in the UI, not Bortle.
- Bin catalog stars in the frame by magnitude (0.5 mag bins).
- **Limiting magnitude** = magnitude where the detected fraction drops below 50%.
- **% lost** = 1 − (detected ÷ expected) for stars brighter than magnitude 6 (naked-eye reference).
- **1–9 score:** map limiting magnitude to 1–9 using a table **calibrated from our own photos** (dark site vs downtown). Treat the table as an estimate and say so in the UI. If we don't have dark-site photos, start from the published naked-eye limiting magnitudes for each Bortle class and adjust once we see real numbers.
- **Camera caveat:** how many stars a photo shows depends on exposure time, ISO and lens, not only the sky. Read exposure time, ISO and f-number from EXIF and store them in `flags`. Lower confidence when they're outside the range our calibration photos used. The UI says the score is "your sky as your phone saw it."
- **Confidence:** high / medium / low, lowered by any warning flag, few matched stars, or unusual exposure settings.

### Condition checks
- Sun altitude > −18° → twilight warning
- Moon altitude > 0° → Moon warning (include illumination %)
- Field-center altitude < 30° → "too close to the horizon" warning

### Failed solves
Return `status: failed` with the detected-star count and a message that very few stars is itself a sign of heavy light pollution. Still allow saving to the map with `confidence: low`.

The job's `error` is `{ code, message, next_step, detected_stars }`; show `message` and `next_step` as written. Codes from the solver: `too_few_stars` (under 12 detections, found in a few seconds), `no_match` (finished without enough evidence), `solve_timeout`, `solver_unavailable` (no `solve-field` and no usable API key), `solve_failed` (API or network error). Upload-time errors (`heic_unsupported`, `not_an_image`, `file_too_large`, `no_capture_time`, `bad_location`, ...) come back as `{ detail: { code, message, next_step } }` with an HTTP error status. `detected_stars` is capped at 2000 and can be `null` when the API solver can't report it.

### AI (explain and communicate — never calculate)
- **Explainer:** input = score, limiting magnitude, % lost, flags, visible constellations/planets, location. Output = short plain-English explanation + what helps (shielded fixtures, warmer bulbs, lights off when not needed).
- **Light-report draft:** input = light category, note, location, nearby score. Output = short, polite, specific request to the relevant office (e.g., UB Facilities, town public works).
- **Never** ask an AI model to identify stars, compute positions or produce a score.
- If the AI call fails or times out, the results page still loads; show the numbers without the explainer.

---

## 5. Conventions (always follow)

- **Time:** store and compute in **UTC (ISO 8601)**. EXIF times often lack a time zone — convert using the device offset. Daylight saving time ends Nov 1, 2026.
- **Angles:** degrees at every API boundary; radians only inside math functions, with names ending `_rad`.
- **Coordinates:** RA/Dec in degrees (J2000). Image pixels: origin top-left, x right, y down, first pixel centre at (0, 0). astrometry.net output for JPEG/PNG needs only a 1-pixel shift and **no y flip**, and the returned WCS works with `origin=0` directly (see §4). Never flip y without re-running the real-photo check in `tests/test_solver_integration.py`.
- **Location data:** iPhones often strip GPS from uploaded photos — use browser geolocation and confirm with the user. Round to ~1 km before storing.
- **Privacy:** strip all EXIF (especially GPS) from every image **before** storing it or sending it to any outside service. Read what we need from EXIF first, then save a stripped copy. The rounded location is the only location we keep.
- **Images:** accept JPEG and PNG. HEIC may fail — show a clear message. Set a max upload size (e.g., 15 MB) and resize very large images before solving.
- **Errors:** every failure the user can hit (HEIC, no stars, location denied, solver timeout, AI down) shows a plain message and a next step, never a blank screen or raw error.
- **Job state** lives in Supabase, not in server memory, so a restart or a second worker doesn't lose jobs.
- **Secrets:** API keys live in `.env` (never committed). Never put keys in frontend code. Provide `.env.example`. Solver settings: `SOLVER_MODE`, `LOCAL_SOLVE_TIMEOUT_S`, `API_SOLVE_TIMEOUT_S`, `ASTROMETRY_API_KEY`, `ASTROMETRY_INDEX_DIR`, `ASTROMETRY_CONFIG` (the Docker image sets the last two; `docker run` needs `--env-file backend/.env` for the API key).
- **Mobile-first:** design and test at ~390 px width first. Every page must work on an iPhone and an Android phone.
- **Demo mode must always work.** Never break or delete `demo_cache/`. Demo results use the exact same JSON shape as real results, and demo mode calls no outside service (no solver, no Claude API).
- **Keep it simple:** no auth, no queues beyond polling, no new dependencies without a stated reason.
- **External APIs and libraries:** check current docs instead of assuming.

---

## 6. Testing

Astronomy bugs are silent — the app "works" but labels are in the wrong place. Test the math against known answers:
- Polaris altitude ≈ observer latitude (UB ≈ 43°N).
- A known star's computed position matches Stellarium for a fixed time and place.
- Projecting a star to pixels and back returns the original RA/Dec.
- Labels near the photo's corners land on their stars (checks the distortion fit).
- **Done (A):** the seven Big Dipper stars (J2000 positions) projected through the solver's returned WCS land within 10 px of a detected star on both local-solve test photos, and within 3.4 px on the nova solve. The brightest detected stars sit on bright pixels, which catches a flipped or shifted axis.
- Sun altitude at local noon is positive; at midnight in November it's below −18° in Buffalo.
- Scoring: a dark-site demo photo scores better than a downtown demo photo.
- Upload edge cases: HEIC, no EXIF, non-sky photo, blurry photo, twilight photo, oversized photo.
- Privacy: a stored image has no GPS EXIF.

Product checks:
- **Judge path:** on a phone that has never opened the site, open the URL → tap "Try a sample photo" → results in under 10 seconds. Run after every deploy.
- **Cold start:** after an hour idle, `/api/health` answers within a few seconds.
- **Solve rate:** run every photo in the test set; record how many solve and how long each takes. Use these numbers in the pitch. So far: 2 of 3 Commons photos solved locally (about 40 s end to end for the one measured through the app); the third did not solve within the time limit. Needs a real test set including phone Night-mode photos.

How to run the solver tests:
- Anywhere: `cd backend && pytest` (solver logic with mocked `solve-field` and mocked nova; real-photo tests skip themselves).
- Real photos, inside Docker: `docker build -t astroscan-backend backend`, then `docker run --rm -v "$PWD/test_photos:/photos:ro" -v "$PWD/backend/tests:/srv/tests:ro" -e TEST_PHOTOS_DIR=/photos astroscan-backend python -m pytest tests/test_solver_integration.py -s`. Photos are `dunes_2048.jpg` and `sandvik_2048.jpg` in git-ignored `test_photos/` (Wikimedia Commons: NPS public domain and CC0; downloaded, then resized by `imaging.strip_and_resize`).

Test real-device flows (upload, geolocation permission, map) on both iOS Safari and Android Chrome.

---

## 7. Timeline and checkpoints

### Setup checklist (the event is today, Nov 7 — project code can be written now)
Do these in hours 0–2, in parallel with the schema work below. Nothing here blocks writing code.
- [ ] Accounts and API keys: Supabase, Vercel, backend host (with the paid or credit-backed instance ready), Anthropic, astrometry.net (done — key works, a real solve ran Nov 7)
- [ ] Every laptop: Docker Desktop (and WSL on Windows), Python, Node, Git
- [ ] Downloads (index files are fetched by the Docker build; two Commons test photos are in `test_photos/` on A's machine only): HYG star catalog, constellation stick-figure lines, wide-field astrometry.net index files, a test photo set (team photos + openly licensed ones, e.g., the Pixel night-sky set on Zenodo — CC BY-NC, so don't commit it)
- [x] Try `solve-field` on one test photo from the command line and note the time (Nov 7: 16–24 s direct, about 40 s through the app, in Docker; see §4)
- [ ] Take Night mode phone photos around campus and somewhere darker as soon as it's dark and clear
- [ ] Assign Persons A–D and fill in names at the top of this file

### Timeline
- **Hour 0–1 (all four):** result JSON schema + one fake result (see §2 "Handoffs").
- **Hour 0–2 (test photos, Person D):** gather a test set of night-sky phone photos with known time and place: the team's own photos and openly licensed ones. Check the Buffalo forecast; if a clear window is coming, plan a campus photo walk for it.
- **Hour 2:** repo set up, blank frontend + backend deployed with HTTPS, API keys working, name decided. A has the public-API client solving a test photo
- **Hour 8:** one photo goes upload → solved → labeled on screen (ugly is fine). Local `solve-field` running in the deployed backend
- **Hour 14:** score, ghost stars and map working
- **Hour 18:** AI explainer, light reports, demo mode and "Try a sample photo" done — **feature freeze**
- **Hour 20:** Devpost draft with screenshots (including an under-the-hood shot) and the solve-rate numbers
- **Hours 18–24:** bug fixes, polish, final deploy, Devpost, demo video (doubles as the backup if Wi-Fi fails), two full pitch rehearsals

**If a checkpoint is missed, cut in this order:** Could features first (light reports down to map pins, then the AI explainer), then Should features (under-the-hood stats, planets, map). Protect the Must features (§2) above everything else.
**Local solver status: working since Nov 7**, so the fallback plan below only applies if it breaks on the deployed host (CPU-starved instance, failed build). **If the local solver isn't working by hour 12:** stay on the public API for the rest of the event, solve the demo photos ahead of time, and lead the pitch with demo mode.

---

## 8. How to work with Claude on this project

- One feature per session. Say which feature (by number above) and which files are in play.
- Stay inside the owner's area (see §2 "Who builds what") unless the change is coordinated. When you start a session, say which person you are.
- Before writing code, briefly state the plan and the files to touch.
- Write or update tests with any math change.
- When something breaks, paste the exact error and, for UI issues, a screenshot.
- Don't add features from the "Out of scope" list. Stretch features only after the hour-16 check.
- All code is written during the event, per hackathon rules.

---

## 9. Judging rubric and pitch

Judging follows past UB Hacking rubrics. What earns each criterion for this project:

| Criterion | What earns it here |
|---|---|
| **It Works** | A live HTTPS URL that works on a judge's own phone. "Try a sample photo" button. Real photos solve fast (local solver). Clear error states. Backend awake during judging |
| **Usefulness** | Two clear users (§1). Real measurements on the map from around campus, not just demo pins. A light report drafted for a real campus light |
| **Technicality** | Plate solving, WCS projection with lens distortion, catalog matching, limiting magnitude. Make it visible: the under-the-hood toggle and one pipeline slide. Mention the known-answer tests |
| **Effort** | Polished mobile UI, tests, real field data, solve-rate numbers, steady commit history |
| **Freshness** | Lead with ghost stars and turning photos into ground-level light pollution data, not "an app that identifies stars" |
| **Pitch** | Structure below; whole team after hour 18; split the speaking parts; two rehearsals; backup video ready |
| **X-Factor** | The ghost-star toggle moment on a real Buffalo photo, plus real campus data gathered during the event |

### Pitch structure (2–3 minutes)
1. **Hook (15 s):** a downtown Buffalo photo on screen, tap the ghost-star toggle: "This is what our sky is hiding."
2. **Problem (20 s):** the sky is getting ~10% brighter per year, and satellites miss most of it.
3. **Demo (60–90 s):** start with a demo-mode result so the full flow is shown no matter what: labels and ghost stars → score → pin on the map → light report draft. Run a live upload only if the local solver reliably finishes in under ~30 s in rehearsal; if it stalls, move on without apologizing.
4. **How it works (20 s):** one sentence on the pipeline, flip the under-the-hood toggle.
5. **Close (15 s):** what we measured this weekend, what's next.

### Judge questions to prepare answers for (keep in /docs)
- "Isn't the score measuring your camera, not the sky?" → yes, partly; we record exposure settings, lower confidence outside our calibration range, and label it an estimate.
- "How accurate is the score?" → calibrated on our own photos; show the dark-site vs downtown comparison.
- "Why not just use satellite maps?" → satellites miss blue LED and sideways light; ground photos fill that gap.
- "What happens with a cloudy or blurry photo?" → show the failed-solve message.
- "Where does user data go?" → EXIF stripped, location rounded to ~1 km, no accounts.
- "Isn't this just Asterism / SkyView?" → those identify stars; we measure light pollution, show the stars it hides, map the results and help people ask for a fix.
