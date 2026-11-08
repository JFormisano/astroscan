"""A real upload reaches /api/map: upload -> (fake) solve -> point. Also privacy and speed of the map."""
import json
import time

import pytest

from app import pipeline, solver
from app.db import LocalStore
from app.light_report_store import LocalReportStore, get_report_store
from app.main import app
from app.routes import measurements
from app.routes.map import FAKE_MAP
from tests.test_measurements import upload


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MAP_SAMPLE_POINTS", "0")  # only real points, to assert on them exactly
    reports = LocalReportStore(tmp_path / "reports")
    app.dependency_overrides[get_report_store] = lambda: reports
    yield
    app.dependency_overrides.pop(get_report_store, None)


def score_block(value=6, confidence="medium"):
    return {"value": value, "limiting_mag": 4.5, "pct_lost": 62.0, "confidence": confidence}


def test_score_columns_copy_the_score_block():
    assert measurements._score_columns({"score": score_block()}) == {
        "score": 6, "limiting_mag": 4.5, "pct_lost": 62.0, "confidence": "medium"}
    assert measurements._score_columns({}) == {}
    assert measurements._score_columns({"score": {"value": None}}) == {}


def test_run_job_stores_score_columns(client, store, monkeypatch):
    real = pipeline.analyze
    monkeypatch.setattr(pipeline, "analyze", lambda r, **k: {**real(r, **k), "score": score_block(7, "high")})
    job = store.get_job(upload(client).json()["job_id"])
    assert (job["score"], job["limiting_mag"], job["pct_lost"], job["confidence"]) == (7, 4.5, 62.0, "high")


def test_uploaded_photo_appears_on_the_map(client, monkeypatch):
    real = pipeline.analyze
    monkeypatch.setattr(pipeline, "analyze", lambda r, **k: {**real(r, **k), "score": score_block(5, "high")})
    job_id = upload(client).json()["job_id"]
    points = client.get("/api/map").json()["measurements"]
    assert points == [{"id": job_id, "lat": 43.0, "lon": -78.79, "score": 5, "confidence": "high",
                       "taken_at_utc": "2026-11-08T02:30:05+00:00", "is_demo": False}]


def test_solved_photo_without_a_score_is_not_on_the_map(client):
    upload(client)  # stub solver, no scoring yet
    assert client.get("/api/map").json()["measurements"] == []


def test_too_few_stars_failure_is_a_grey_point(client, monkeypatch):
    def few(*a, **k):
        raise solver.too_few_stars(4)

    monkeypatch.setattr(solver, "solve", few)
    job_id = upload(client).json()["job_id"]
    (point,) = client.get("/api/map").json()["measurements"]
    assert point["id"] == job_id and point["score"] is None and point["confidence"] == "low"


def test_other_failures_are_not_on_the_map(client, monkeypatch):
    monkeypatch.setattr(solver, "solve", lambda *a, **k: (_ for _ in ()).throw(solver.no_match(300)))
    upload(client)
    assert client.get("/api/map").json()["measurements"] == []


def test_map_leaks_nothing_private(client, monkeypatch):
    real = pipeline.analyze
    monkeypatch.setattr(pipeline, "analyze", lambda r, **k: {**real(r, **k), "score": score_block()})
    upload(client)
    text = client.get("/api/map").text
    for secret in ("Pixel", "Google", "make_model", "exposure_s", "iso", "image_url", "/image",
                   "result", "flags", "error", "78.7897", "43.0008", "limiting_mag", "pct_lost"):
        assert secret not in text, secret
    (point,) = json.loads(text)["measurements"]
    assert set(point) == {"id", "lat", "lon", "score", "confidence", "taken_at_utc", "is_demo"}


def test_map_stays_fast_with_hundreds_of_big_jobs(tmp_path, capsys):
    from fastapi.testclient import TestClient

    store = LocalStore(tmp_path)
    blob = {"sources": [{"x": i, "y": i, "flux": 1.0} for i in range(1000)], "pad": "x" * 150_000}
    for i in range(200):
        job = store.create_job({"taken_at_utc": "2026-11-08T02:30:05+00:00", "lat_rounded": 43.0,
                                "lon_rounded": -78.79}, b"x")
        store.update_job(job["id"], {"status": "solved", "score": 1 + i % 9, "confidence": "high",
                                     "result": blob})
    from app.db import get_store
    app.dependency_overrides[get_store] = lambda: store
    try:
        c = TestClient(app)
        c.get("/api/map")
        t0 = time.perf_counter()
        for _ in range(5):
            body = c.get("/api/map").json()
        per_request = (time.perf_counter() - t0) / 5
    finally:
        app.dependency_overrides.pop(get_store, None)
    assert len(body["measurements"]) == 200
    with capsys.disabled():
        print(f"\n/api/map with 200 x ~{len(json.dumps(blob))//1024} KB jobs: {per_request*1000:.1f} ms")
    assert per_request < 0.25
