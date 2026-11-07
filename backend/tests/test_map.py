import pytest
from fastapi.testclient import TestClient

from app.light_report_store import LocalReportStore, get_report_store
from app.main import app
from app.routes import map as map_routes


@pytest.fixture
def report_store(tmp_path):
    store = LocalReportStore(tmp_path)
    app.dependency_overrides[get_report_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_report_store, None)


@pytest.fixture
def client(report_store):
    return TestClient(app)


def _report(store, **overrides):
    fields = {"lat_rounded": 43.0, "lon_rounded": -78.79, "category": "floodlight",
              "controller": "ub", "note": "Very bright", "drafted_message": "Hello",
              "draft_source": "template", "measurement_id": None}
    return store.create({**fields, **overrides}, None)


def test_map_returns_points(client):
    res = client.get("/api/map")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"measurements", "light_reports"}
    for m in body["measurements"]:
        assert {"id", "lat", "lon", "score", "confidence", "taken_at_utc", "is_demo"} <= set(m)
        assert m["score"] is None or 1 <= m["score"] <= 9


def test_measurements_are_fake_until_db_can_list_them(client):
    assert client.get("/api/map").json()["measurements"] == map_routes.FAKE_MAP["measurements"]


def test_real_light_reports_appear_on_the_map(client, report_store):
    assert client.get("/api/map").json()["light_reports"] == []
    report = _report(report_store)
    points = client.get("/api/map").json()["light_reports"]
    assert len(points) == 1
    assert points[0]["id"] == report["id"]
    assert points[0]["category_label"] == "Floodlight or security light"
    assert {"lat", "lon", "note", "created_at"} <= set(points[0])
    assert "drafted_message" not in points[0]  # the map shows the light, not the letter


def test_locations_rounded_to_about_1km():
    assert map_routes.round_location(43.002871) == 43.0
    assert map_routes.round_location(-78.789412) == -78.79
    assert map_routes.round_location(None) is None


def test_db_rows_are_rounded_and_missing_locations_skipped(client, monkeypatch):
    rows = [
        {"id": "a", "lat_rounded": 43.00456, "lon_rounded": -78.7891, "score": 5,
         "confidence": "high", "taken_at_utc": "2026-11-07T03:00:00Z", "is_demo": False},
        {"id": "b", "lat_rounded": None, "lon_rounded": None, "score": 4},
    ]
    monkeypatch.setattr(map_routes, "_load_measurement_rows", lambda: rows)
    body = client.get("/api/map").json()
    assert body["measurements"] == [
        {"id": "a", "lat": 43.0, "lon": -78.79, "score": 5, "confidence": "high",
         "taken_at_utc": "2026-11-07T03:00:00Z", "is_demo": False}
    ]


def test_each_source_falls_back_on_its_own(client, report_store, monkeypatch):
    _report(report_store)

    def boom(*_args):
        raise RuntimeError("db down")

    monkeypatch.setattr(map_routes, "_load_measurement_rows", boom)
    body = client.get("/api/map").json()
    assert body["measurements"] == map_routes.FAKE_MAP["measurements"]
    assert len(body["light_reports"]) == 1

    monkeypatch.setattr(map_routes, "_load_report_rows", boom)
    res = client.get("/api/map")
    assert res.status_code == 200
    assert res.json()["light_reports"] == []
