from fastapi.testclient import TestClient

from app.main import app


def test_health():
    res = TestClient(app).get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_reports_which_solver_photos_will_use(monkeypatch):
    from app import solver

    monkeypatch.setattr(solver, "local_available", lambda: True)
    monkeypatch.delenv("SOLVER_MODE", raising=False)
    monkeypatch.delenv("ASTROMETRY_API_KEY", raising=False)
    info = TestClient(app).get("/api/health").json()["solver"]
    assert info["using"] == "local" and info["mode"] == "auto" and info["api_key_set"] is False


def test_solver_status_decision_table(monkeypatch):
    from app import solver

    def using(mode, local, key):
        monkeypatch.setenv("SOLVER_MODE", mode)
        monkeypatch.setattr(solver, "local_available", lambda: local)
        if key:
            monkeypatch.setenv("ASTROMETRY_API_KEY", "k")
        else:
            monkeypatch.delenv("ASTROMETRY_API_KEY", raising=False)
        return solver.status()["using"]

    assert using("auto", True, True) == "local"
    assert using("auto", False, True) == "api"
    assert using("auto", False, False) == "none"
    assert using("local", False, True) == "none"  # local mode never uses the API
    assert using("api", True, False) == "none"
    assert using("api", True, True) == "api"
    assert using("stub", True, True) == "stub"


def test_health_never_leaks_the_api_key(monkeypatch):
    monkeypatch.setenv("ASTROMETRY_API_KEY", "super-secret-key-123")
    assert "super-secret-key-123" not in TestClient(app).get("/api/health").text
