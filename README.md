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

## Layout
- `frontend/` React + Vite. Pages in `src/pages/`, components in `src/components/`, all backend calls in `src/api.js`.
- `backend/` FastAPI. `app/` modules, `data/` star catalog and constellation lines, `demo_cache/` pre-solved results (never delete), `tests/`.
- `docs/` result schema, pitch notes, judge Q&A.

## Team
Person A (photo in, solve out) · Person B (astronomy math) · Person C (main user flow) · Person D (map, reports, AI, demo). Ownership is in CLAUDE.md §2.
