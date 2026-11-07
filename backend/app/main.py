"""App setup. Owner: Person A. Includes the routers from app/routes/."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import demo, light_reports, map as map_routes, measurements

load_dotenv()

app = FastAPI(title="AstroScan API")

# Comma-separated list of allowed frontend origins (set FRONTEND_ORIGINS in prod).
origins = os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(measurements.router, prefix="/api")
app.include_router(map_routes.router, prefix="/api")
app.include_router(light_reports.router, prefix="/api")
app.include_router(demo.router, prefix="/api")


@app.get("/api/health")
def health():
    """Keep-alive ping and quick deploy check."""
    return {"status": "ok"}
