# AstroScan (working name)

Free, mobile-first website: upload a night-sky photo, get stars and constellations labeled, a 1–9 sky quality score, the "ghost stars" light pollution hides, a shared map, and an AI-drafted light report. Built at UB Hacking 2026. Scope, architecture and conventions live in [CLAUDE.md](CLAUDE.md).

## Run locally

Backend (http://localhost:8000):
```
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp .env.example .env, then fill in keys
uvicorn app.main:app --reload
pytest
```

Frontend (http://localhost:5173, proxies /api to the backend):
```
cd frontend
npm install
npm run dev
```

## Run the solver in Docker (plate solving, feature #2)
The real star matching uses astrometry.net's `solve-field`, which only exists in the Docker image (it downloads ~46 MB of index files on the first build). Without it the backend falls back to the public astrometry.net API (needs `ASTROMETRY_API_KEY` in `backend/.env`), or set `SOLVER_MODE=stub` for a fake result.
```
docker build -t astroscan-backend backend
docker run --rm -p 8000:8000 --env-file backend/.env astroscan-backend

# real-photo tests (photos live in git-ignored test_photos/, see docs/solver-output.md)
docker run --rm -v "$PWD/test_photos:/photos:ro" -v "$PWD/backend/tests:/srv/tests:ro" -e TEST_PHOTOS_DIR=/photos astroscan-backend python -m pytest tests/test_solver_integration.py -s
```
What the solver returns and how pixels map to the sky: [docs/solver-output.md](docs/solver-output.md).

## Layout
- `frontend/` React + Vite. Pages in `src/pages/`, components in `src/components/`, all backend calls in `src/api.js`.
- `backend/` FastAPI. `app/` modules, `data/` star catalog and constellation lines, `demo_cache/` pre-solved results (never delete), `tests/`.
- `docs/` result schema, pitch notes, judge Q&A.

## Team
Person A (photo in, solve out) · Person B (astronomy math) · Person C (main user flow) · Person D (map, reports, AI, demo). Ownership is in CLAUDE.md §2.
