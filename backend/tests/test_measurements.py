import io
import json

import pytest
from PIL import Image

from app import solver
from app.db import LocalStore
from app.main import app
from app.routes import measurements
from tests.conftest import make_photo


def upload(client, data=None, *, lat="43.0008", lon="-78.7897", name="sky.jpg", **extra):
    data = make_photo() if data is None else data
    fields = {"lat": lat, "lon": lon, **extra}
    return client.post("/api/measurements", files={"image": (name, data, "image/jpeg")}, data=fields)


def test_upload_then_poll_reaches_solved(client):
    res = upload(client)
    assert res.status_code == 201
    job_id = res.json()["job_id"]

    body = client.get(f"/api/measurements/{job_id}").json()
    assert body["status"] == "solved"  # TestClient runs the background task before returning
    assert body["result"]["stub"] is True
    assert body["error"] is None
    assert body["lat"] == 43.0 and body["lon"] == -78.79
    assert body["taken_at_utc"].startswith("2026-11-08T02:30:05")
    assert body["flags"]["solver_used"] == "stub"
    assert "solve_seconds" in body["flags"]


def test_flags_hold_camera_settings(client):
    job_id = upload(client).json()["job_id"]
    flags = client.get(f"/api/measurements/{job_id}").json()["flags"]
    assert flags["iso"] == 800
    assert flags["exposure_s"] == pytest.approx(1 / 3)
    assert flags["f_number"] == pytest.approx(1.8)
    assert flags["taken_at_source"] == "exif+exif_offset"
    assert (flags["image_w"], flags["image_h"]) == (400, 300)


def test_privacy_stored_image_and_job_have_no_gps(client, store, tmp_path):
    job_id = upload(client, lat="43.000834", lon="-78.789722").json()["job_id"]

    stored = (tmp_path / "images" / f"{job_id}.jpg").read_bytes()
    img = Image.open(io.BytesIO(stored))
    assert len(img.getexif()) == 0
    assert not img.getexif().get_ifd(0x8825)
    assert b"Exif" not in stored[:64]

    # exact coordinates are not stored anywhere on disk
    job_json = (tmp_path / "jobs" / f"{job_id}.json").read_text()
    assert "43.000834" not in job_json and "78.789722" not in job_json
    assert json.loads(job_json)["lat_rounded"] == 43.0


def test_image_endpoint_serves_stripped_photo(client):
    job_id = upload(client).json()["job_id"]
    body = client.get(f"/api/measurements/{job_id}").json()
    res = client.get(body["image_url"])
    assert res.status_code == 200 and res.headers["content-type"] == "image/jpeg"


def test_client_time_fallback_when_no_exif_time(client):
    photo = make_photo(taken=None, offset=None)
    assert upload(client, photo).status_code == 422  # nothing to go on
    res = upload(client, photo, taken_at="2026-11-08T02:30:05Z")
    assert res.status_code == 201


def test_no_capture_time_error_shape(client):
    res = upload(client, make_photo(taken=None, offset=None))
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "no_capture_time" and detail["message"] and detail["next_step"]


def test_exif_time_with_client_offset(client):
    job_id = upload(client, make_photo(offset=None), tz_offset_minutes="-300").json()["job_id"]
    body = client.get(f"/api/measurements/{job_id}").json()
    assert body["taken_at_utc"].startswith("2026-11-08T02:30:05")
    assert body["flags"]["taken_at_source"] == "exif+client_offset"


def test_heic_rejected_with_plain_message(client):
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 200
    res = upload(client, heic, name="IMG_1.HEIC")
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "heic_unsupported"
    assert res.json()["detail"]["next_step"]


def test_text_file_renamed_jpg_rejected(client):
    res = upload(client, b"hello, I am not a photo" * 50, name="photo.jpg")
    assert res.status_code == 415 and res.json()["detail"]["code"] == "not_an_image"


def test_oversized_upload_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.01")  # ~10 KB
    big = make_photo(size=(1200, 900))
    assert len(big) > 11_000
    res = upload(client, big)
    assert res.status_code == 413 and res.json()["detail"]["code"] == "file_too_large"


def test_empty_upload_rejected(client):
    res = upload(client, b"")
    assert res.status_code == 422 and res.json()["detail"]["code"] == "not_an_image"


@pytest.mark.parametrize("lat,lon", [("95", "0"), ("0", "200"), ("north", "west")])
def test_bad_location_rejected(client, lat, lon):
    res = upload(client, lat=lat, lon=lon)
    assert res.status_code == 422 and res.json()["detail"]["code"] == "bad_location"


def test_unknown_job_is_404_with_plain_message(client):
    for job_id in ["00000000-0000-4000-8000-000000000000", "not-a-uuid"]:
        res = client.get(f"/api/measurements/{job_id}")
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "job_not_found"
    assert client.get("/api/measurements/nope/image").status_code == 404


def test_solver_failure_becomes_failed_job(client, monkeypatch):
    def boom(*a, **k):
        raise solver.SolveFailed("Too few stars to identify.", "Try Night mode.", detected_stars=3)

    monkeypatch.setattr(solver, "solve", boom)
    body = client.get(f"/api/measurements/{upload(client).json()['job_id']}").json()
    assert body["status"] == "failed"
    assert body["error"]["detected_stars"] == 3
    assert body["error"]["message"] and body["error"]["next_step"]


def test_unexpected_solver_crash_never_leaves_job_pending(client, monkeypatch):
    def crash(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(solver, "solve", crash)
    body = client.get(f"/api/measurements/{upload(client).json()['job_id']}").json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "internal_error"
    assert "kaboom" not in json.dumps(body)  # no raw error text reaches the user


def test_stale_pending_jobs_fail_on_restart(tmp_path):
    store = LocalStore(tmp_path)
    pending = store.create_job({"taken_at_utc": "2026-11-08T02:30:05+00:00", "lat_rounded": 43.0, "lon_rounded": -78.79}, b"x")
    done = store.create_job({"status": "solved"}, b"x")
    assert store.mark_stale_pending_failed() == 1
    assert store.get_job(pending["id"])["status"] == "failed"
    assert store.get_job(pending["id"])["error"]["code"] == "server_restarted"
    assert store.get_job(done["id"])["status"] == "solved"


def test_job_state_survives_new_store_instance(client, tmp_path):
    job_id = upload(client).json()["job_id"]
    assert LocalStore(tmp_path).get_job(job_id)["status"] == "solved"


def test_steps_are_reported_while_solving(client, store, monkeypatch):
    seen = []

    def spy(path, lat, lon, taken_at, on_step=None):
        assert path.exists()
        on_step("Finding stars…")
        seen.append(store.get_job(job_id_holder["id"]).get("step"))
        return {"ok": True}

    job_id_holder = {}
    original = measurements.run_job

    def capture(store_, job_id, image_bytes):
        job_id_holder["id"] = job_id
        original(store_, job_id, image_bytes)

    monkeypatch.setattr(solver, "solve", spy)
    monkeypatch.setattr(measurements, "run_job", capture)
    upload(client)
    assert seen == ["Finding stars…"]
