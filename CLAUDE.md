# CLAUDE.md — UB Hacking: Light Pollution Sky App

> Read this whole file at the start of every session. It is the source of truth for scope, architecture and conventions. If a request conflicts with this file, point out the conflict before writing code.

Working name: **TBD — pick by hour 2** (needed for the domain, Devpost and pitch; judges remember names)
Event: UB Hacking (24 hours) — team of 4
Team: Person A (photo in, solve out) · Person B (astronomy math) · Person C (main user flow) · Person D (map, reports, AI, demo) — *fill in names*. Full split in §2 "Who builds what".
Pitch: the whole team works on it together after the hour-18 feature freeze.

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
- **Hour 8:** A's solver output → B's matching and scoring → C's results page. First real photo on screen.
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
- **Backend:** Python + FastAPI in a Docker image that includes astrometry.net's `solve-field` and only the wide-field index files. `astropy` (WCS projection), `numpy`, `Pillow` (EXIF), `astronomy-engine` (Sun/Moon/planets).
- **Database / storage:** Supabase.
- **AI:** Anthropic API, called **only from the backend**. Check docs.claude.com for current model names.
- **Hosting:** Vercel free tier (frontend). Backend on a host with real CPU. HTTPS is required.
  - `solve-field` is CPU-bound. Render's free tier gives 0.1 CPU and 512 MB RAM and spins down after 15 minutes idle (about a minute to wake), so a solve there would be far too slow. Use a paid instance with at least 0.5–1 CPU for the weekend (Render Starter is $7/month with 0.5 CPU and no spin-down), or sponsor cloud credits if the event offers them.
  - Run **one worker** and one solve at a time; parallel solves on a small machine just make every solve slower.
  - **The backend must not sleep during judging.** Use an always-on instance; keep `/api/health` for a quick check.

### Proposed layout
```
/frontend
  src/pages/        Landing, Upload, Processing, Results, Map, LightReport
  src/components/   SkyOverlay, ScoreCard, WarningBanner, MapView, UnderTheHood
  src/api.js        all backend calls in one place
/backend
  Dockerfile        includes solve-field + wide-field index files
  app/main.py       app setup; includes the routers below (A)
  app/routes/       measurements.py (A) · map.py, light_reports.py, demo.py (D)
  app/solver.py     local solve-field + astrometry.net API fallback
  app/matching.py
  app/scoring.py
  app/conditions.py
  app/ai.py
  app/db.py
  data/             star catalog (filtered HYG), constellation lines JSON
  demo_cache/       pre-solved demo results (do not delete)
  tests/
/docs               spec, pitch notes, judge Q&A
```

### API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/measurements` | multipart image + lat, lon, taken_at → `{ job_id }` |
| GET | `/api/measurements/{job_id}` | `{ status: pending\|solved\|failed, step?, result? }` |
| GET | `/api/map` | measurements + light reports for the map |
| POST | `/api/light-reports` | photo + lat, lon, category, note → report + drafted message |
| GET | `/api/demo/{name}` | cached demo result, same shape as a real result |
| GET | `/api/health` | for the keep-alive ping and a quick deploy check |

### Data model (Supabase)
- **measurements:** id, created_at, status (pending|solved|failed), taken_at_utc, lat_rounded, lon_rounded, score, limiting_mag, pct_lost, confidence, flags (jsonb — includes exposure_s, iso, f_number, solve_seconds, solver_used), image_url (EXIF-stripped copy), solved (bool), is_demo (bool)
- **light_reports:** id, created_at, lat_rounded, lon_rounded, photo_url (EXIF-stripped copy), category, note, drafted_message, measurement_id (nullable)

---

## 4. How the core works

### Plate solving
**Order of work:** build the public-API client first, because it already works (test on Nov 7: login OK, 11 s queue, but about 10 minutes until a result). That gets real solves flowing to B and C by hour 8. Get the local solver running in parallel and make it the primary as soon as it works. `solver.py` hides which solver ran, so nothing else changes when we switch.

**Goal primary: run astrometry.net locally.** `solve-field` in the backend's Docker image, with only the wide-field 4100-series index files a phone photo needs (about 100 MB; phone fields are tens of degrees across, so the multi-GB telescope index sets aren't needed). This removes our dependence on the public server, which can be slow, queued or down during a hackathon weekend, and makes a live solve in front of judges realistic.
- Pass a scale hint and downsample large images; both speed up the solve a lot. **Phone EXIF focal lengths are unreliable** (a Pixel 9 reports a ~74° field when the saved photo really spans ~38°, because of cropping), so use a lopsided range around the EXIF estimate (roughly 0.35× to 1.2×), with a wide fallback (e.g., 10–100°).
- Fit a distortion model (SIP, tweak order 2–3) because phone lenses distort toward the edges, which would otherwise put labels in the wrong place.
- **Fail fast:** count detected stars first (about a second) and reject photos with almost none instead of letting them run to a timeout. Set our own solve time limit (e.g., 60–90 s) and report "timed out" separately from "no match found."
- **Don't trust the exit code alone:** `solve-field` can report success for a wrong match built from very few stars. Accept a solve only if enough stars matched (start with ≥ 8) and the match confidence is high; check the exact output fields in the docs and tune on our test set.

**Fallback: public nova.astrometry.net API.** Flow: log in with API key → upload image → get submission ID → poll for job ID → poll job status → fetch results. Upload with `publicly_visible` set to no — public submissions can be seen by anyone, and the photo would carry the user's location. Solves can take many minutes, so in the app, give up after a few minutes and show the failure message.

Either way we need: the **WCS solution** (maps sky coordinates ↔ image pixels), the **list of extracted sources** (detected stars in pixels) and optionally its **annotations**. **Confirm exact flags, endpoints and output files against current astrometry.net docs** — don't guess.

### Star matching
1. Load catalog stars (filtered HYG, roughly magnitude ≤ 7).
2. Project each into image pixels with the WCS (`astropy.wcs`), loading the full WCS file so the distortion (SIP) terms are applied. Keep those inside the frame.
3. A catalog star is **detected** if an extracted source lies within N pixels (start with ~3–5 px; tune on our photos; may need a larger radius near the edges). **Phone Night mode stacks many frames and can shift stars by up to ~1° in parts of the image**, so test on Night mode photos early. If labels drift, snap each label to the nearest detected star within a larger radius rather than writing a full correction model.
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

### AI (explain and communicate — never calculate)
- **Explainer:** input = score, limiting magnitude, % lost, flags, visible constellations/planets, location. Output = short plain-English explanation + what helps (shielded fixtures, warmer bulbs, lights off when not needed).
- **Light-report draft:** input = light category, note, location, nearby score. Output = short, polite, specific request to the relevant office (e.g., UB Facilities, town public works).
- **Never** ask an AI model to identify stars, compute positions or produce a score.
- If the AI call fails or times out, the results page still loads; show the numbers without the explainer.

---

## 5. Conventions (always follow)

- **Time:** store and compute in **UTC (ISO 8601)**. EXIF times often lack a time zone — convert using the device offset. Daylight saving time ends Nov 1, 2026.
- **Angles:** degrees at every API boundary; radians only inside math functions, with names ending `_rad`.
- **Coordinates:** RA/Dec in degrees (J2000). Image pixels: origin top-left, x right, y down (convert from FITS conventions explicitly and comment it).
- **Location data:** iPhones often strip GPS from uploaded photos — use browser geolocation and confirm with the user. Round to ~1 km before storing.
- **Privacy:** strip all EXIF (especially GPS) from every image **before** storing it or sending it to any outside service. Read what we need from EXIF first, then save a stripped copy. The rounded location is the only location we keep.
- **Images:** accept JPEG and PNG. HEIC may fail — show a clear message. Set a max upload size (e.g., 15 MB) and resize very large images before solving.
- **Errors:** every failure the user can hit (HEIC, no stars, location denied, solver timeout, AI down) shows a plain message and a next step, never a blank screen or raw error.
- **Job state** lives in Supabase, not in server memory, so a restart or a second worker doesn't lose jobs.
- **Secrets:** API keys live in `.env` (never committed). Never put keys in frontend code. Provide `.env.example`.
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
- Sun altitude at local noon is positive; at midnight in November it's below −18° in Buffalo.
- Scoring: a dark-site demo photo scores better than a downtown demo photo.
- Upload edge cases: HEIC, no EXIF, non-sky photo, blurry photo, twilight photo, oversized photo.
- Privacy: a stored image has no GPS EXIF.

Product checks:
- **Judge path:** on a phone that has never opened the site, open the URL → tap "Try a sample photo" → results in under 10 seconds. Run after every deploy.
- **Cold start:** after an hour idle, `/api/health` answers within a few seconds.
- **Solve rate:** run every photo in the test set; record how many solve and how long each takes. Use these numbers in the pitch.

Test real-device flows (upload, geolocation permission, map) on both iOS Safari and Android Chrome.

---

## 7. Timeline and checkpoints

### Setup checklist (the event is today, Nov 7 — project code can be written now)
Do these in hours 0–2, in parallel with the schema work below. Nothing here blocks writing code.
- [ ] Accounts and API keys: Supabase, Vercel, backend host (with the paid or credit-backed instance ready), Anthropic, astrometry.net (done — login tested Nov 7)
- [ ] Every laptop: Docker Desktop (and WSL on Windows), Python, Node, Git
- [ ] Downloads: HYG star catalog, constellation stick-figure lines, wide-field astrometry.net index files, a test photo set (team photos + openly licensed ones, e.g., the Pixel night-sky set on Zenodo — CC BY-NC, so don't commit it)
- [ ] Try `solve-field` on one test photo from the command line and note the time
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
**If the local solver isn't working by hour 12:** stay on the public API for the rest of the event, solve the demo photos ahead of time, and lead the pitch with demo mode.

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
