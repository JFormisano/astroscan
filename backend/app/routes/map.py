"""Routes for map. Owner: Person D. See the API table in CLAUDE.md section 3.

GET /api/map returns every measurement and light report as map points:

    {
      "measurements": [
        {"id", "lat", "lon", "score" (1-9 or null for a failed solve),
         "confidence" ("high"|"medium"|"low"), "taken_at_utc" (ISO 8601 UTC), "is_demo"}
      ],
      "light_reports": [
        {"id", "lat", "lon", "category", "note", "created_at"}
      ]
    }

Locations are always rounded to ~1 km (2 decimal places) before they leave the
backend, even if the stored value was not (CLAUDE.md section 5, "Location data").
"""
from fastapi import APIRouter

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
         "note": "Unshielded parking lot floodlight", "created_at": "2026-11-07T05:00:00Z"},
    ],
}


def round_location(value):
    """Round a latitude or longitude (degrees) to ~1 km."""
    return None if value is None else round(float(value), ROUND_DECIMALS)


def _load_rows():
    """Return (measurement_rows, light_report_rows) from Supabase, or None if not available.

    TODO(Person D): once Person A's app/db.py exposes a Supabase client, query:
      measurements:  id, lat_rounded, lon_rounded, score, confidence, taken_at_utc, is_demo
                     where status in ('solved', 'failed')
      light_reports: id, lat_rounded, lon_rounded, category, note, created_at
    """
    return None


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
        "note": row.get("note"),
        "created_at": row.get("created_at"),
    }


@router.get("/map")
def get_map():
    """All measurements and light reports for the map."""
    try:
        rows = _load_rows()
    except Exception as exc:  # database down: keep the map working with fake points
        print(f"[map] Supabase query failed, serving fake data: {exc}")
        rows = None

    if rows is None:
        return FAKE_MAP

    measurements, reports = rows
    return {
        "measurements": [_measurement_point(r) for r in measurements
                         if r.get("lat_rounded") is not None and r.get("lon_rounded") is not None],
        "light_reports": [_report_point(r) for r in reports
                          if r.get("lat_rounded") is not None and r.get("lon_rounded") is not None],
    }
