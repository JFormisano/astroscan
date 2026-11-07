"""Routes for light_reports. Owner: Person D (#9). See the API table in CLAUDE.md section 3.

POST /api/light-reports            photo (optional) + lat, lon, category, controller, note
                                   -> the stored report, including an AI-drafted message
GET  /api/light-reports/{id}/photo the stripped photo (local store only; Supabase serves its own URL)

We never send email. The user copies the drafted message and sends it themselves.
Privacy (CLAUDE.md section 5): the photo is checked, stripped of all EXIF (incl. GPS) and resized
before it's stored; coordinates are rounded to ~1 km before anything else sees them.
"""
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app import ai, imaging
from app.report_templates import CATEGORIES, RECIPIENTS, category_label
from app.errors import ApiError
from app.light_report_store import ReportStore, get_report_store

log = logging.getLogger(__name__)
router = APIRouter()

# Light types and recipients (keys, labels, wording) live in app/report_templates.py.
NOTE_MAX_CHARS = 500
_CHUNK = 1024 * 1024


def _max_upload_bytes() -> int:
    return int(float(os.environ.get("MAX_UPLOAD_MB", "15")) * 1024 * 1024)


def _read_photo(photo: UploadFile | None) -> bytes | None:
    """Read the optional photo with a size cap. An empty file part counts as no photo."""
    if photo is None:
        return None
    limit = _max_upload_bytes()
    chunks, total = [], 0
    while chunk := photo.file.read(_CHUNK):
        total += len(chunk)
        if total > limit:
            raise ApiError(
                413,
                "file_too_large",
                f"That photo is larger than {limit / (1024 * 1024):g} MB.",
                "Choose a smaller photo, or send the report without one.",
            )
        chunks.append(chunk)
    return b"".join(chunks) or None


def _clean_photo(raw: bytes) -> bytes:
    """Checked, EXIF-free, resized JPEG. Reuses Person A's helpers (app/imaging.py)."""
    try:
        imaging.sniff_format(raw)
    except ApiError as exc:
        if exc.code == "not_an_image":  # reword: this isn't a night-sky upload
            raise ApiError(415, "not_an_image", "That file isn't a JPEG or PNG photo.",
                           "Choose a JPEG or PNG photo of the light, or send the report without one.") from None
        raise
    clean, _w, _h = imaging.strip_and_resize(raw)
    return clean


def _nearby_score(measurement_id: str | None) -> int | None:
    """Score of the measurement this report came from, if one was given and has a score."""
    if not measurement_id:
        return None
    try:
        from app.db import get_store

        job = get_store().get_job(measurement_id)
        if not job:
            return None
        score = job.get("score")
        if score is None:
            score = ((job.get("result") or {}).get("score") or {}).get("value")
        return int(score) if score is not None and 1 <= int(score) <= 9 else None
    except Exception:  # a missing score must never block a report
        log.warning("[light-reports] could not read score for %s", measurement_id)
        return None


def _public(report: dict) -> dict:
    return {
        "id": report["id"],
        "created_at": report.get("created_at"),
        "lat": report["lat_rounded"],
        "lon": report["lon_rounded"],
        "category": report["category"],
        "category_label": category_label(report["category"]),
        "controller": report.get("controller", "unknown"),
        "note": report.get("note"),
        "photo_url": report.get("photo_url"),
        "drafted_message": report["drafted_message"],
        "draft_source": report.get("draft_source", "template"),
        "measurement_id": report.get("measurement_id"),
    }


@router.post("/light-reports", status_code=201)
def create_light_report(
    lat: str = Form(...),
    lon: str = Form(...),
    category: str = Form(...),
    controller: str = Form("unknown"),
    note: str | None = Form(None),
    measurement_id: str | None = Form(None),
    photo: UploadFile | None = File(None),
    store: ReportStore = Depends(get_report_store),
):
    # Sync route on purpose: FastAPI runs it in a thread, so the AI call doesn't block other requests.
    lat_r, lon_r = imaging.parse_location(lat, lon)  # raw coordinates end here

    if category not in CATEGORIES:
        raise ApiError(422, "bad_category", "Please pick what kind of light this is.",
                       "Choose one of the light types and try again.")
    if controller not in RECIPIENTS:
        controller = "unknown"
    note = (note or "").strip() or None
    if note and len(note) > NOTE_MAX_CHARS:
        raise ApiError(422, "note_too_long", f"Please keep the note under {NOTE_MAX_CHARS} characters.",
                       "Shorten the note and try again.")
    try:
        measurement_id = str(uuid.UUID(measurement_id)) if measurement_id else None
    except ValueError:
        measurement_id = None  # e.g. a demo result: not a real stored measurement

    raw = _read_photo(photo)
    clean = _clean_photo(raw) if raw else None
    del raw

    message, source = ai.draft_light_report(
        category=category,
        controller=controller,
        note=note,
        lat=lat_r,
        lon=lon_r,
        nearby_score=_nearby_score(measurement_id),
    )

    report = store.create(
        {
            "lat_rounded": lat_r,
            "lon_rounded": lon_r,
            "category": category,
            "controller": controller,
            "note": note,
            "drafted_message": message,
            "draft_source": source,
            "measurement_id": measurement_id,
        },
        clean,
    )
    return _public(report)


@router.get("/light-reports/{report_id}/photo")
def get_light_report_photo(report_id: str, store: ReportStore = Depends(get_report_store)):
    path = store.photo_path(report_id)
    if path is None:
        raise ApiError(404, "photo_not_found", "We couldn't find that photo.", "")
    return FileResponse(path, media_type="image/jpeg")
