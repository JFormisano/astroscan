"""Routes for measurements. Owner: Person A. See the API table in CLAUDE.md section 3.

POST /api/measurements              upload a photo -> { job_id }
GET  /api/measurements/{job_id}     poll status / fetch the result
GET  /api/measurements/{job_id}/image  the stripped photo (LocalStore only; Supabase serves its own URL)
"""
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from app import imaging, pipeline, solver
from app.db import Store, get_store
from app.errors import ApiError

router = APIRouter()
log = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


def _max_upload_bytes() -> int:
    return int(float(os.environ.get("MAX_UPLOAD_MB", "15")) * 1024 * 1024)


def _too_large(limit_mb: float) -> ApiError:
    return ApiError(
        413,
        "file_too_large",
        f"That photo is larger than {limit_mb:g} MB.",
        "Choose a smaller photo, or export a lower-quality JPEG, and try again.",
    )


async def _read_limited(file: UploadFile, request: Request) -> bytes:
    limit = _max_upload_bytes()
    limit_mb = limit / (1024 * 1024)
    declared = request.headers.get("content-length")
    # Multipart overhead is tiny; allow a little slack, then check the real byte count below.
    if declared and declared.isdigit() and int(declared) > limit + 64 * 1024:
        raise _too_large(limit_mb)
    chunks, total = [], 0
    while chunk := await file.read(_CHUNK):
        total += len(chunk)
        if total > limit:
            raise _too_large(limit_mb)
        chunks.append(chunk)
    if total == 0:
        raise ApiError(422, "not_an_image", "No photo was received.", "Choose a photo and try again.")
    return b"".join(chunks)


def _score_columns(result: dict) -> dict:
    """Copy the score block's headline numbers to the job's top-level columns (what /api/map reads).

    `result["score"]` comes from Person B's scoring.score_sky ({value, limiting_mag, pct_lost,
    confidence, ...}) once it is wired into the pipeline; without it there is nothing to copy.
    """
    block = result.get("score")
    if not isinstance(block, dict) or block.get("value") is None:
        return {}
    return {
        "score": block["value"],
        "limiting_mag": block.get("limiting_mag"),
        "pct_lost": block.get("pct_lost"),
        "confidence": block.get("confidence"),
    }


def run_job(store: Store, job_id: str, image_bytes: bytes) -> None:
    """Background task: solve one job and record the outcome. Never leaves a job `pending`."""
    t0 = time.monotonic()
    tmp_path: Path | None = None
    try:
        job = store.get_job(job_id)
        if job is None:
            return
        # The solver wants a file on disk; the stripped copy is small, so write a temp one.
        # (solver.solve serialises local solves itself; see solver._local_lock.)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)
        taken_at = datetime.fromisoformat(job["taken_at_utc"])
        result = solver.solve(
            tmp_path,
            job["lat_rounded"],
            job["lon_rounded"],
            taken_at,
            on_step=lambda s: store.update_job(job_id, {"step": s}),
            hints=job.get("flags") or {},
        )
        # Add star names, constellation lines, planets, warnings and the score (Person B's matching/conditions/scoring).
        # Never fails the job: a photo that solved stays solved even if these extras break.
        result = pipeline.analyze(
            result,
            lat=job["lat_rounded"],
            lon=job["lon_rounded"],
            taken_at_utc=job["taken_at_utc"],
            image_url=job.get("image_url"),
            exif=job.get("flags") or {},
            image_path=tmp_path,
            on_step=lambda s: store.update_job(job_id, {"step": s}),
        )
        flags = {**(job.get("flags") or {}), "solve_seconds": round(time.monotonic() - t0, 2)}
        flags["solver_used"] = result.get("solver_used", flags.get("solver_used"))
        fields = {"status": "solved", "solved": True, "step": None, "result": result, "flags": flags}
        fields.update(_score_columns(result))
        store.update_job(job_id, fields)
    except solver.SolveFailed as e:
        error = {"code": e.code, "message": e.message, "next_step": e.next_step, "detected_stars": e.detected_stars}
        fields = {"status": "failed", "step": None, "error": error}
        if e.code == "too_few_stars":
            fields["confidence"] = "low"  # still goes on the map as a grey dot (CLAUDE.md section 4)
        store.update_job(job_id, fields)
    except Exception:  # anything unexpected: plain message in the UI, full traceback in the server log
        log.exception("Job %s crashed", job_id)
        store.update_job(
            job_id,
            {
                "status": "failed",
                "step": None,
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong while processing your photo.",
                    "next_step": "Please try again in a moment.",
                },
            },
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _int_or_none(text: str | None) -> int | None:
    try:
        return int(float(text)) if text not in (None, "") else None
    except ValueError:
        return None


@router.post("/measurements", status_code=201)
async def create_measurement(
    request: Request,
    background: BackgroundTasks,
    image: UploadFile = File(...),
    lat: str = Form(...),
    lon: str = Form(...),
    taken_at: str | None = Form(None),
    tz_offset_minutes: str | None = Form(None),
    store: Store = Depends(get_store),
):
    """Upload a photo. `taken_at` is an ISO 8601 fallback if EXIF has no time;
    `tz_offset_minutes` is the device's offset in minutes EAST of UTC (JS: -getTimezoneOffset())."""
    raw = await _read_limited(image, request)
    imaging.sniff_format(raw)  # rejects HEIC / non-images before anything else

    lat_r, lon_r = imaging.parse_location(lat, lon)  # raw coords end here; only rounded go on

    # Read what we need from EXIF FIRST, then build the stripped copy and drop the raw bytes.
    exif = imaging.read_exif(raw)
    taken_utc, taken_source = imaging.resolve_taken_at(exif, taken_at, _int_or_none(tz_offset_minutes))
    clean_bytes, width, height = imaging.strip_and_resize(raw)
    del raw

    flags = {
        "exposure_s": exif["exposure_s"],
        "iso": exif["iso"],
        "f_number": exif["f_number"],
        "focal_length_mm": exif["focal_length_mm"],
        "focal_35mm": exif["focal_35mm"],
        "make_model": exif["make_model"],
        "image_w": width,
        "image_h": height,
        "taken_at_source": taken_source,
    }
    job = store.create_job(
        {
            "taken_at_utc": taken_utc.isoformat(),
            "lat_rounded": lat_r,
            "lon_rounded": lon_r,
            "step": "Reading photo",
            "flags": flags,
        },
        clean_bytes,
    )
    background.add_task(run_job, store, job["id"], clean_bytes)
    return {"job_id": job["id"]}


@router.get("/measurements/{job_id}")
def get_measurement(job_id: str, store: Store = Depends(get_store)):
    job = store.get_job(job_id)
    if job is None:
        raise ApiError(
            404,
            "job_not_found",
            "We couldn't find that result.",
            "It may have expired. Upload your photo again to get a new result.",
        )
    return {
        "job_id": job["id"],
        "status": job["status"],
        "step": job.get("step"),
        "result": job.get("result"),
        "error": job.get("error"),
        "image_url": job.get("image_url"),
        "taken_at_utc": job.get("taken_at_utc"),
        "lat": job.get("lat_rounded"),
        "lon": job.get("lon_rounded"),
        "flags": job.get("flags"),
    }


@router.get("/measurements/{job_id}/image")
def get_measurement_image(job_id: str, store: Store = Depends(get_store)):
    path = store.image_path(job_id)
    if path is None:
        raise ApiError(404, "job_not_found", "We couldn't find that photo.", "Upload your photo again.")
    return FileResponse(path, media_type="image/jpeg")
