# Run and deploy AstroScan

Owner: Person A. Two goals: run everything on your own PC with one command, and put the same thing on the internet with a few clicks.

```
browser ──► frontend (React, static)  ──/api──►  backend (FastAPI + solve-field)  ──►  Supabase (jobs + photos)
            Vercel in production                  Render in production                    optional locally
            nginx in docker compose               Docker image: backend/Dockerfile
```

## 1. Run it on your own PC

You need Docker Desktop. Nothing else (no Python, Node or astrometry install).

```
docker compose up --build        # first build takes a few minutes (it downloads ~46 MB of star-index files), later starts take seconds
```
Open **http://localhost:8080**. Stop with `Ctrl+C`; `docker compose down` removes the containers (your jobs stay in the `astroscan_storage` volume; `docker compose down -v` wipes them).

| URL | What |
|---|---|
| http://localhost:8080 | the app (nginx serves the built React app and forwards `/api` to the backend, like production) |
| http://localhost:8000/docs | the backend's interactive API docs |
| http://localhost:8000/api/health | health check |

No `.env` is needed: the local solver needs no key. To add keys (nova fallback, Supabase, AI), `copy backend\.env.example backend\.env` (macOS/Linux: `cp`), fill it in and run `docker compose up -d --build backend`. Don't add `ASTROMETRY_INDEX_DIR` or `ASTROMETRY_CONFIG` to `.env`; the image sets them and an empty value would break the solver.

**Check that it works** (needs the backend venv, see README; use any JPEG of the night sky):
```
cd backend
python scripts/smoke.py http://localhost:8080 ../test_photos/dunes_2048.jpg   # expect: solved, ~40 s
python scripts/smoke.py http://localhost:8080 --blank                           # expect: failed cleanly in ~2 s
```

**Run the tests** (all of them, including real `solve-field` runs on the photos in `test_photos/`):
```
docker compose --profile test run --rm --build tests
```
Without Docker: `cd backend && pytest` runs the logic tests only (the real-solver ones skip).

**Editing code with live reload** (faster than rebuilding): run the backend in Docker and the frontend dev server on your machine.
```
docker compose up -d backend
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api to localhost:8000
```
Frontend-only work with no backend: put `VITE_FAKE_API=1` in `frontend/.env.local` (fake results, see `frontend/src/fake/`).

## 2. Deploy everything on one server (recommended)

One Linux server runs the whole app with the real `solve-field`, HTTPS and nothing else to sign up for. This is the simplest way to get a public site that uses the real solver, and it is what to rehearse before a demo.

**What you need:** a Linux server with Docker (Ubuntu 24.04 works), **1-2 CPUs and 2 GB RAM** (the solver is single-threaded and CPU-bound; peak memory was about 290 MiB in testing), about 3 GB of disk, ports 80 and 443 open, and a domain name whose DNS **A record points at the server's IP**. Without a domain, use Render + Vercel below, or `docker compose up` on a machine you can reach directly over plain HTTP.

```
# 1. on the server: install Docker (official script) and open the web ports
curl -fsSL https://get.docker.com | sh
sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable      # if you use ufw

# 2. get the code
git clone https://github.com/JFormisano/astroscan.git && cd astroscan

# 3. settings: the domain, and (optionally) keys
echo "DOMAIN=astroscan.example.com" > .env                 # root .env: used by compose itself
cp backend/.env.example backend/.env                        # then edit: ASTROMETRY_API_KEY, SUPABASE_*, ANTHROPIC_API_KEY (all optional)

# 4. build and start (first build downloads the star-index files; a few minutes)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
`docker-compose.prod.yml` adds Caddy, which gets and renews the HTTPS certificate by itself, hides the backend and frontend ports so only 80/443 are reachable, and tells the backend to accept browsers from `https://<DOMAIN>`. Caddy needs a few seconds after the first start to get its certificate.

**Prove it is using the real solver** (from your own computer, with the backend venv, see README):
```
cd backend
python scripts/smoke.py https://astroscan.example.com --require-local                     # fails unless the real solver is in use
python scripts/smoke.py https://astroscan.example.com ../test_photos/dunes_2048.jpg --require-local   # + a full upload and solve
```
The health check says it directly: open `https://<DOMAIN>/api/health` and look for `"solver": {"using": "local", "local_available": true, "index_files": 10}`. `using` means:

| `using` | Meaning |
|---|---|
| `local` | the real `solve-field` is installed with its index files and will be used |
| `api` | `solve-field` is missing, so photos go to the public nova.astrometry.net API (needs `ASTROMETRY_API_KEY`; slow and queue-dependent) |
| `stub` | `SOLVER_MODE=stub`: fake results. Never in production |
| `none` | no solver at all: every photo fails with `solver_unavailable` |

If it says anything but `local` on a server built from this repo, look for a `SOLVER_MODE` line in `backend/.env`, or a build that failed to download the index files (`docker compose logs backend`, `docker compose build --no-cache backend`).

**Day-to-day:**
```
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend      # watch solves and errors
git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build   # deploy new code
docker compose -f docker-compose.yml -f docker-compose.prod.yml down                 # stop (data stays)
```
Containers restart by themselves after a crash or a server reboot. **Re-measure the solve time on the server** with the smoke test (about 40 s on a fast desktop core; a slower server needs a larger `LOCAL_SOLVE_TIMEOUT_S` in `backend/.env`, default 90). Photos and results live in the Docker volume `astroscan_storage` on that server. For results that survive losing the server, add Supabase (section 3a) and set the two `SUPABASE_*` values in `backend/.env`.

**Test the production setup on your own PC first** (this is how it was checked): `DOMAIN=localhost docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`, then `python scripts/smoke.py https://localhost --require-local --insecure` (`--insecure` only because Caddy uses a self-signed certificate for `localhost`). Bring your normal setup back with `docker compose up -d` after `down`.

## 3. Deploy as two services (Render + Vercel)

Order matters only in one place: the frontend needs the backend's URL, and the backend needs the frontend's URL (for CORS). Deploy the backend first, then the frontend, then paste the frontend URL back into the backend.

### 3a. Supabase (jobs and photos survive restarts)
1. New project at supabase.com. SQL editor → paste and run `backend/supabase/schema.sql` (creates the `measurements` table and a public `images` bucket), then `backend/supabase/light_reports.sql` (the `light_reports` table the light-report feature needs).
2. Settings → API: copy the project URL and the **service_role** key (a secret; backend only, never the frontend).

Heads up: the Supabase code path (`SupabaseStore` in `backend/app/db.py`) is written but has **not been run against a real project yet**. The smoke test in step d is how you find out. Without Supabase the backend still works, but jobs live on the instance's disk and a result link dies when the service redeploys.

### 3b. Backend on Render
1. Render → **New → Blueprint** → select this repo. It reads `render.yaml`.
2. Fill in the prompted values: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ASTROMETRY_API_KEY` (optional fallback), `ANTHROPIC_API_KEY` (later), and `FRONTEND_ORIGINS` (put a placeholder like `http://localhost:5173` for now).
3. Deploy. The first build takes several minutes (it downloads the index files). Note the URL: `https://astroscan-backend-xxxx.onrender.com`.
4. Check: `python scripts/smoke.py https://astroscan-backend-xxxx.onrender.com ../test_photos/dunes_2048.jpg`. **Record the solve time** on this instance and compare with the ~40 s from a fast PC; if it's near `LOCAL_SOLVE_TIMEOUT_S` (120), pick a bigger plan.

The blueprint uses `plan: 1c-2g` (1 CPU, 2 GB) because the solver is CPU-bound; check Render's pricing page for the cost, and `0.5c-512mb` is the cheaper option if you accept roughly 2x slower solves. Never use the free plan (0.1 CPU, sleeps after 15 min idle).

### 3c. Frontend on Vercel
1. Vercel → **Add New → Project** → import this repo.
2. **Root Directory: `frontend`**. Framework preset: Vite (also set in `frontend/vercel.json`, which makes `/results/<id>` links survive a refresh).
3. Environment variable: `VITE_API_URL` = the Render URL from step b (no trailing slash). It is public by design; never put secrets in `VITE_*` variables.
4. Deploy. Note the URL: `https://astroscan.vercel.app`.

### 3d. Close the loop
1. Render → backend → Environment → set `FRONTEND_ORIGINS` to the exact Vercel origin (comma-separate several, e.g. a custom domain). No trailing slash. Save; it redeploys.
2. Open the Vercel URL on a phone that has never seen it and upload a photo. Then run the checks from CLAUDE.md §6: judge path, cold start (`smoke.py` health time after an hour idle), solve time.

Vercel preview deployments get their own URLs; add them to `FRONTEND_ORIGINS` only if you need to test them.

### Any other Docker host (Fly.io, Railway)
The backend is one image (`backend/Dockerfile`) that listens on `$PORT` (default 8000), contains `solve-field` and its index files, and has a health check at `/api/health`. Give it 1 CPU / 2 GB and the environment variables from section 4, then run `smoke.py <url> --require-local` against it. For a single VPS use section 2 instead.

## 4. Environment variables

| Variable | Where | Meaning |
|---|---|---|
| `DOMAIN` | root `.env` (compose) | the site's domain name for the one-server setup (section 2) |
| `SOLVER_MODE` | backend | `auto` (default), `local`, `api`, `stub`; see `docs/solver-output.md` |
| `LOCAL_SOLVE_TIMEOUT_S` | backend | local solve limit, default 90 (the blueprint uses 120) |
| `API_SOLVE_TIMEOUT_S` | backend | public API give-up time, default 240 |
| `ASTROMETRY_API_KEY` | backend | nova.astrometry.net key for the fallback |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | backend | both set → Supabase; otherwise local disk |
| `STORAGE_DIR` | backend | local-disk location (the image sets `/srv/storage`) |
| `MAP_SAMPLE_POINTS` | backend | `0` hides the fake sample dots on `/map` (default shows them after the real ones). Set it to `0` for the judged deployment |
| `FRONTEND_ORIGINS` | backend | allowed browser origins (CORS), comma-separated |
| `MAX_UPLOAD_MB` | backend | upload limit, default 15 |
| `ANTHROPIC_API_KEY` | backend | AI explainer and report drafts (Person D) |
| `VITE_API_URL` | frontend build | backend origin; empty = same origin (compose/nginx) |
| `VITE_FAKE_API` | frontend dev | `1` = fake results, no backend |

## 5. When something is off

| Symptom | Likely cause |
|---|---|
| Browser console shows a CORS error | `FRONTEND_ORIGINS` doesn't exactly match the page's origin (scheme, host, no trailing slash) |
| App loads but every request fails | `VITE_API_URL` missing or wrong at **build** time; change it in Vercel and redeploy |
| Refreshing `/results/<id>` gives a 404 | `frontend/vercel.json` not picked up: Root Directory must be `frontend` |
| Photos fail with `solver_unavailable` | not running the Docker image (no `solve-field`) and no `ASTROMETRY_API_KEY`; check `/api/health` -> `solver.using` |
| `/api/health` says `using: api` or `none` on your own server | `solve-field` or its index files are missing in the running image; rebuild without cache, and check `SOLVER_MODE` in `backend/.env` |
| HTTPS doesn't come up on the server | the domain's A record doesn't point at the server yet, or ports 80/443 are blocked; `docker compose ... logs caddy` shows the certificate attempts |
| Every solve ends `solve_timeout` | instance too slow; raise `LOCAL_SOLVE_TIMEOUT_S` or the plan |
| Results vanish after a deploy | no Supabase configured, so jobs were on the instance's disk |
| `docker compose ... up` says `required variable DOMAIN is missing` | create the root `.env` with `DOMAIN=...` or prefix the command with `DOMAIN=...` |
| `docker compose up` says `backend` unhealthy | `docker compose logs backend`; a bad `.env` line is the usual cause |
