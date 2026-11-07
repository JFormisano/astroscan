"""Demo mode (#11): cached results must always load, in the same shape as a real result."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import demo

client = TestClient(app)

DEMO_FILES = sorted(demo.DEMO_DIR.glob("*.json"))
# Same top-level keys GET /api/measurements/{job_id} returns.
JOB_KEYS = {"job_id", "status", "step", "result", "error", "image_url", "taken_at_utc", "lat", "lon", "flags"}


def test_demo_cache_is_not_empty():
    assert DEMO_FILES, "demo_cache/ needs at least one result (run scripts/make_demo_cache.py)"


@pytest.mark.parametrize("path", DEMO_FILES, ids=lambda p: p.stem)
def test_demo_result_shape(path):
    res = client.get(f"/api/demo/{path.stem}")
    assert res.status_code == 200
    job = res.json()
    assert job == json.loads(path.read_text(encoding="utf-8"))
    assert JOB_KEYS <= set(job)
    assert job["job_id"] == f"demo-{path.stem}"
    assert job["is_demo"] is True
    assert job["status"] in ("solved", "failed")
    if job["status"] == "failed":
        return

    result = job["result"]
    w, h = result["image"]["width"], result["image"]["height"]
    assert 1 <= result["score"]["value"] <= 9
    assert result["score"]["confidence"] in ("high", "medium", "low")
    assert 0 <= result["score"]["pct_lost"] <= 100
    assert result["stars"], "a solved demo needs stars"
    for s in result["stars"]:
        assert 0 <= s["x"] <= w and 0 <= s["y"] <= h
        assert isinstance(s["detected"], bool)
    assert any(not s["detected"] for s in result["stars"]), "ghost stars are the demo centerpiece"
    assert result["explainer"], "demo results carry cached AI text"


def test_dark_site_scores_better_than_downtown():
    """CLAUDE.md section 6: a dark-site demo photo scores better than a downtown one."""
    dark = client.get("/api/demo/dark-site").json()["result"]["score"]
    city = client.get("/api/demo/buffalo-downtown").json()["result"]["score"]
    assert dark["value"] < city["value"]  # 1 = darkest
    assert dark["limiting_mag"] > city["limiting_mag"]
    assert dark["pct_lost"] < city["pct_lost"]


@pytest.mark.parametrize("name", ["does-not-exist", ".env", "UPPER", "a" * 80])
def test_unknown_or_bad_name_is_404(name):
    res = client.get(f"/api/demo/{name}")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "demo_not_found"


def test_path_traversal_is_404():
    # The router never matches an encoded slash to {name}; either way nothing outside demo_cache is read.
    assert client.get("/api/demo/..%2F..%2F.env").status_code == 404
    assert demo.NAME_RE.match("../../.env") is None


def test_demo_uses_no_outside_services(monkeypatch):
    """Demo mode never touches the store, solver or Claude API."""
    from app import db

    def boom(*_args, **_kwargs):
        raise AssertionError("demo mode must not call outside services")

    monkeypatch.setattr(db, "get_store", boom)
    assert client.get("/api/demo/buffalo-downtown").status_code == 200
