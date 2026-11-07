"""App setup. Owner: Person A. Includes the routers from app/routes/."""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import get_store
from app.errors import ApiError
from app.routes import demo, light_reports, map as map_routes, measurements

load_dotenv()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Jobs left `pending` by a previous process will never finish; fail them with a clear message.
    try:
        count = get_store().mark_stale_pending_failed()
        if count:
            log.warning("Marked %d stale pending job(s) as failed after restart", count)
    except Exception:
        log.exception("Could not check for stale jobs at startup")
    yield


app = FastAPI(title="AstroScan API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError):
    """Every user-facing failure: {"detail": {"code", "message", "next_step"}}."""
    return JSONResponse(status_code=exc.status, content={"detail": exc.to_detail()})


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
