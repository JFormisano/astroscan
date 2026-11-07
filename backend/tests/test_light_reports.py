"""Light reports (#9): validation, privacy, AI fallback, storage."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import ai, report_templates
from app.light_report_store import LocalReportStore, get_report_store
from app.main import app
from tests.conftest import make_photo

FORM = {"lat": "43.002871", "lon": "-78.789412", "category": "floodlight", "controller": "ub",
        "note": "Unshielded light pointing at the sky all night"}


@pytest.fixture
def report_store(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # tests never call the real API
    store = LocalReportStore(tmp_path)
    app.dependency_overrides[get_report_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_report_store, None)


@pytest.fixture
def client(report_store):
    return TestClient(app)


def post(client, data=None, photo=None, name="light.jpg"):
    files = {"photo": (name, photo, "image/jpeg")} if photo is not None else None
    return client.post("/api/light-reports", data=data or FORM, files=files)


def test_report_without_photo(client, report_store):
    res = post(client)
    assert res.status_code == 201
    body = res.json()
    assert body["lat"] == 43.0 and body["lon"] == -78.79  # rounded to ~1 km
    assert body["photo_url"] is None
    assert body["category_label"] == "Floodlight or security light"
    assert body["draft_source"] == "template"  # no API key
    assert "UB Facilities" in body["drafted_message"]
    assert "Unshielded light" in body["drafted_message"]
    assert report_store.list()[0]["id"] == body["id"]


def test_raw_coordinates_are_never_stored(client, report_store):
    post(client)
    saved = json.dumps(report_store.list())
    assert "43.002871" not in saved and "78.789412" not in saved


def test_photo_is_stored_without_exif(client, report_store):
    res = post(client, photo=make_photo(gps=True))
    assert res.status_code == 201
    body = res.json()
    assert body["photo_url"] == f"/api/light-reports/{body['id']}/photo"

    served = client.get(body["photo_url"])
    assert served.status_code == 200
    img = Image.open(io.BytesIO(served.content))
    assert not img.getexif()  # no EXIF at all, so no GPS
    assert report_store.photo_path(body["id"]).read_bytes() == served.content


def test_empty_photo_part_counts_as_no_photo(client):
    res = post(client, photo=b"")
    assert res.status_code == 201
    assert res.json()["photo_url"] is None


def test_heic_photo_gets_a_clear_message(client, report_store):
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    res = post(client, photo=heic, name="light.heic")
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "heic_unsupported"
    assert report_store.list() == []


def test_non_image_gets_a_clear_message(client):
    res = post(client, photo=b"hello, not a photo")
    assert res.status_code == 415
    detail = res.json()["detail"]
    assert detail["code"] == "not_an_image"
    assert "without one" in detail["next_step"]


def test_photo_too_large(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")
    res = post(client, photo=make_photo(size=(800, 600)))
    assert res.status_code == 413


@pytest.mark.parametrize("field,value,code", [
    ("lat", "not-a-number", "bad_location"),
    ("lat", "123", "bad_location"),
    ("category", "laser", "bad_category"),
    ("note", "x" * 501, "note_too_long"),
])
def test_bad_input(client, field, value, code):
    res = post(client, data={**FORM, field: value})
    assert res.status_code in (400, 422)
    assert res.json()["detail"]["code"] == code


def test_unknown_controller_falls_back(client):
    body = post(client, data={**FORM, "controller": "aliens"}).json()
    assert body["controller"] == "unknown"
    assert "pass this along" in body["drafted_message"]


def test_demo_measurement_id_is_ignored(client):
    body = post(client, data={**FORM, "measurement_id": "demo-buffalo-downtown"}).json()
    assert body["measurement_id"] is None


def test_ai_draft_is_used_when_available(client, monkeypatch):
    calls = {}

    def fake_draft(**kwargs):
        calls.update(kwargs)
        return "Dear UB Facilities, ...", "ai"

    monkeypatch.setattr(ai, "draft_light_report", fake_draft)
    body = post(client).json()
    assert body["drafted_message"] == "Dear UB Facilities, ..."
    assert body["draft_source"] == "ai"
    assert calls["lat"] == 43.0  # the AI only ever sees the rounded location
    assert calls["controller"] == "ub" and calls["category"] == "floodlight"


def test_ai_failure_falls_back_to_template(monkeypatch):
    """With a key set but the API failing, the user still gets a message."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class Boom:
        def __init__(self, *a, **k):
            raise ai.anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(ai.anthropic, "Anthropic", Boom)
    text, source = ai.draft_light_report(category="streetlight", controller="ub",
                                         note=None, lat=43.0, lon=-78.79)
    assert source == "template"
    assert text.startswith("Hello UB Facilities,")


def test_template_is_the_free_default(client):
    """No key: the template writes every draft, specific to the light and the recipient."""
    body = post(client, data={**FORM, "category": "sign", "controller": "business"}).json()
    assert body["draft_source"] == "template"
    msg = body["drafted_message"]
    assert "night mode" in msg  # sign-specific fix
    assert "electricity bills" in msg  # business-specific closing
    assert "Approximate location: 43.00, -78.79" in msg


@pytest.mark.parametrize("category", sorted(report_templates.CATEGORIES))
@pytest.mark.parametrize("controller", sorted(report_templates.RECIPIENTS))
def test_every_template_combination_is_complete(category, controller):
    msg = report_templates.light_report_message(category=category, controller=controller,
                                                note="Too bright", lat=43.0, lon=-78.79)
    assert "{" not in msg and "}" not in msg  # no unfilled placeholders
    assert msg.startswith(report_templates.RECIPIENTS[controller]["greeting"])
    assert msg.rstrip().endswith("A neighbor")
    for fix in report_templates.CATEGORIES[category]["fixes"]:
        assert fix[1:] in msg
    assert 60 <= len(msg.split()) <= 220  # short enough to actually get read


def test_each_light_type_has_its_own_fixes():
    fixes = [tuple(c["fixes"]) for c in report_templates.CATEGORIES.values()]
    assert len(set(fixes)) == len(fixes)


def test_template_mentions_nearby_score():
    msg = report_templates.light_report_message(category="streetlight", controller="ub", note=None,
                                                lat=43.0, lon=-78.79, nearby_score=7)
    assert "7 out of 9" in msg


def test_unknown_keys_fall_back_to_generic_wording():
    msg = report_templates.light_report_message(category="laser", controller="aliens", note=None,
                                                lat=43.0, lon=-78.79)
    assert "an outdoor light" in msg and "pass this along" in msg


def test_missing_photo_is_404(client):
    assert client.get("/api/light-reports/not-a-uuid/photo").status_code == 404
    assert client.get("/api/light-reports/00000000-0000-0000-0000-000000000000/photo").status_code == 404
