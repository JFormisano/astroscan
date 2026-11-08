"""Routes for map. Owner: Person D. See the API table in CLAUDE.md section 3.

GET /api/map returns every measurement and light report as map points:

    {
      "measurements": [
        {"id", "lat", "lon", "score" (1-9 or null for a failed solve),
         "confidence" ("high"|"medium"|"low"), "taken_at_utc" (ISO 8601 UTC), "is_demo"}
      ],
      "light_reports": [
        {"id", "lat", "lon", "category", "category_label", "note", "created_at"}
      ]
    }

Light reports are real (app/light_report_store.py). Measurements are real too (Store.list_map_points
in app/db.py: solved jobs with a score, and "too few stars" failures as score null). FAKE_MAP's
sample points (is_demo true, "Sample data" popup) follow the real ones so a fresh deploy's map isn't
empty; set MAP_SAMPLE_POINTS=0 to drop them. If the store fails, only the sample points are served
(or nothing, with the switch off).

Locations are always rounded to ~1 km (2 decimal places) before they leave the
backend, even if the stored value was not (CLAUDE.md section 5, "Location data").
"""
import logging
import os

from fastapi import APIRouter, Depends

from app.db import Store, get_store
from app.light_report_store import ReportStore, get_report_store
from app.report_templates import category_label

log = logging.getLogger(__name__)
router = APIRouter()

# ~1.1 km of latitude per 0.01 degree. Matches lat_rounded / lon_rounded in Supabase.
ROUND_DECIMALS = 2

# Fake points around Buffalo so the map can be built before Supabase is wired up
# (CLAUDE.md section 2, "Handoffs"). Same shape as the real response.
FAKE_MAP = {
    "measurements": [
        {"id": "fake-ub-north", "lat": 43.00, "lon": -78.79, "score": 6,
         "confidence": "medium", "taken_at_utc": "2026-11-07T03:00:00Z", "is_demo": True},
        {"id": "fake-downtown", "lat": 42.89, "lon": -78.88, "score": 8,
         "confidence": "high", "taken_at_utc": "2026-11-07T03:30:00Z", "is_demo": True},
        {"id": "fake-dark-site", "lat": 42.73, "lon": -78.47, "score": 3,
         "confidence": "medium", "taken_at_utc": "2026-11-07T04:10:00Z", "is_demo": True},
        {"id": "fake-failed", "lat": 42.96, "lon": -78.82, "score": None,
         "confidence": "low", "taken_at_utc": "2026-11-07T04:30:00Z", "is_demo": True},
    ],
    "light_reports": [
        {"id": "fake-report-1", "lat": 43.00, "lon": -78.78, "category": "floodlight",
         "category_label": "Floodlight or security light",
         "note": "Unshielded parking lot floodlight", "created_at": "2026-11-07T05:00:00Z"},
    ],
}


def round_location(value):
    """Round a latitude or longitude (degrees) to ~1 km."""
    return None if value is None else round(float(value), ROUND_DECIMALS)


def _load_measurement_rows(store: Store):
    """Real measurement rows from Person A's store (rounded location, score, confidence, time, is_demo)."""
    return store.list_map_points()


def _sample_points():
    """The fake sample points, unless MAP_SAMPLE_POINTS=0 switches them off."""
    if os.environ.get("MAP_SAMPLE_POINTS", "1").strip().lower() in ("0", "false", "no", "off"):
        return []
    return FAKE_MAP["measurements"]


def _load_report_rows(store):
    """Light report rows from our own store (app/light_report_store.py)."""
    return store.list()


def _measurement_point(row):
    return {
        "id": row["id"],
        "lat": round_location(row["lat_rounded"]),
        "lon": round_location(row["lon_rounded"]),
        "score": row.get("score"),
        "confidence": row.get("confidence") or "low",
        "taken_at_utc": row.get("taken_at_utc"),
        "is_demo": bool(row.get("is_demo")),
    }


def _report_point(row):
    return {
        "id": row["id"],
        "lat": round_location(row["lat_rounded"]),
        "lon": round_location(row["lon_rounded"]),
        "category": row.get("category"),
        "category_label": category_label(row.get("category")),
        "note": row.get("note"),
        "created_at": row.get("created_at"),
    }


def _has_location(row):
    return row.get("lat_rounded") is not None and row.get("lon_rounded") is not None


@router.get("/map")
def get_map(
    report_store: ReportStore = Depends(get_report_store),
    store: Store = Depends(get_store),
):
    """All measurements and light reports for the map.

    Each half falls back on its own, so one failing source never blanks the whole map:
    measurements fall back to the sample points, light reports to an empty list.
    """
    try:
        measurement_rows = _load_measurement_rows(store)
    except Exception:
        log.exception("[map] measurement query failed, serving fake measurements")
        measurement_rows = None
    try:
        report_rows = _load_report_rows(report_store)
    except Exception:
        log.exception("[map] light report query failed")
        report_rows = []

    if measurement_rows is None:
        measurements = _sample_points()  # store unavailable: never blank the whole map
    else:
        real = [_measurement_point(r) for r in measurement_rows if _has_location(r)]
        measurements = real + _sample_points()
    return {
        "measurements": measurements,
        "light_reports": [_report_point(r) for r in report_rows if _has_location(r)],
    }
