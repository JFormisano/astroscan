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

Light reports are real (app/light_report_store.py). Measurements are FAKE_MAP's sample points
until Person A's store can list jobs (see _load_measurement_rows).

Locations are always rounded to ~1 km (2 decimal places) before they leave the
backend, even if the stored value was not (CLAUDE.md section 5, "Location data").
"""
import logging

from fastapi import APIRouter, Depends

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


def _load_measurement_rows():
    """Measurement rows from Person A's store, or None while that isn't available.

    TODO(Person D): once app/db.py can list jobs (ask Person A), return rows with
    id, lat_rounded, lon_rounded, score, confidence, taken_at_utc, is_demo
    for status in ('solved', 'failed'). Until then the map shows the fake measurements.
    """
    return None


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
def get_map(report_store: ReportStore = Depends(get_report_store)):
    """All measurements and light reports for the map.

    Each half falls back on its own, so one failing source never blanks the whole map:
    measurements fall back to the fake points, light reports to an empty list.
    """
    try:
        measurement_rows = _load_measurement_rows()
    except Exception:
        log.exception("[map] measurement query failed, serving fake measurements")
        measurement_rows = None
    try:
        report_rows = _load_report_rows(report_store)
    except Exception:
        log.exception("[map] light report query failed")
        report_rows = []

    if measurement_rows is None:
        measurements = FAKE_MAP["measurements"]
    else:
        measurements = [_measurement_point(r) for r in measurement_rows if _has_location(r)]
    return {
        "measurements": measurements,
        "light_reports": [_report_point(r) for r in report_rows if _has_location(r)],
    }
