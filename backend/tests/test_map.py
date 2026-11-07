from fastapi.testclient import TestClient

from app.main import app
from app.routes import map as map_routes


def test_map_returns_points():
    res = TestClient(app).get("/api/map")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"measurements", "light_reports"}
    for m in body["measurements"]:
        assert {"id", "lat", "lon", "score", "confidence", "taken_at_utc", "is_demo"} <= set(m)
        assert m["score"] is None or 1 <= m["score"] <= 9
    for r in body["light_reports"]:
        assert {"id", "lat", "lon", "category", "note"} <= set(r)


def test_locations_rounded_to_about_1km():
    assert map_routes.round_location(43.002871) == 43.0
    assert map_routes.round_location(-78.789412) == -78.79
    assert map_routes.round_location(None) is None


def test_db_rows_are_rounded_and_missing_locations_skipped(monkeypatch):
    rows = (
        [
            {"id": "a", "lat_rounded": 43.00456, "lon_rounded": -78.7891, "score": 5,
             "confidence": "high", "taken_at_utc": "2026-11-07T03:00:00Z", "is_demo": False},
            {"id": "b", "lat_rounded": None, "lon_rounded": None, "score": 4},
        ],
        [],
    )
    monkeypatch.setattr(map_routes, "_load_rows", lambda: rows)
    body = TestClient(app).get("/api/map").json()
    assert body["measurements"] == [
        {"id": "a", "lat": 43.0, "lon": -78.79, "score": 5, "confidence": "high",
         "taken_at_utc": "2026-11-07T03:00:00Z", "is_demo": False}
    ]


def test_db_failure_falls_back_to_fake_data(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(map_routes, "_load_rows", boom)
    res = TestClient(app).get("/api/map")
    assert res.status_code == 200
    assert res.json() == map_routes.FAKE_MAP
