"""Store.list_map_points: which jobs reach the public map, and that nothing private comes with them."""
import json

import pytest

from app.db import MAP_POINT_FIELDS, LocalStore, SupabaseStore

BASE = {"taken_at_utc": "2026-11-08T02:30:05+00:00", "lat_rounded": 43.0, "lon_rounded": -78.79}


def make(store, status, *, score=None, confidence=None, error=None, **extra):
    job = store.create_job({**BASE, "flags": {"make_model": "Google Pixel 9"}, **extra}, b"x")
    fields = {"status": status, "score": score, "confidence": confidence, "error": error,
              "result": {"big": "blob"}}
    store.update_job(job["id"], fields)
    return job["id"]


def few_stars():
    return {"code": "too_few_stars", "message": "m", "next_step": "n", "detected_stars": 3}


def test_only_the_right_jobs_are_listed(store):
    ok = make(store, "solved", score=6, confidence="high")
    gray = make(store, "failed", error=few_stars())
    make(store, "solved")  # solved but no score yet
    make(store, "failed", error={"code": "solve_timeout", "message": "m", "next_step": "n"})
    make(store, "failed", error={"code": "no_match", "message": "m", "next_step": "n"})
    make(store, "failed", error={"code": "internal_error", "message": "m", "next_step": "n"})
    store.create_job(BASE, b"x")  # pending
    points = {p["id"]: p for p in store.list_map_points()}
    assert set(points) == {ok, gray}
    assert points[ok]["score"] == 6 and points[ok]["confidence"] == "high"
    assert points[gray]["score"] is None and points[gray]["confidence"] == "low"


def test_points_have_only_the_public_fields(store):
    make(store, "solved", score=4, confidence="medium")
    make(store, "failed", error=few_stars())
    for p in store.list_map_points():
        assert tuple(p) == MAP_POINT_FIELDS
        assert p["lat_rounded"] == 43.0 and p["is_demo"] is False


def test_newest_first_and_limit(store):
    ids = [make(store, "solved", score=n, confidence="high") for n in (1, 2, 3)]
    listed = [p["id"] for p in store.list_map_points()]
    assert listed == list(reversed(ids))
    assert [p["id"] for p in store.list_map_points(limit=2)] == listed[:2]


def test_listing_does_not_read_job_files(store, monkeypatch):
    make(store, "solved", score=5, confidence="high")
    monkeypatch.setattr(type(store), "get_job", lambda *a: pytest.fail("read a job file"))
    assert len(store.list_map_points()) == 1


def test_index_survives_restart(store, tmp_path):
    jid = make(store, "solved", score=5, confidence="high")
    assert [p["id"] for p in LocalStore(tmp_path).list_map_points()] == [jid]


def test_index_is_rebuilt_from_job_files_when_missing_or_damaged(store, tmp_path):
    jid = make(store, "solved", score=5, confidence="high")
    (tmp_path / "jobs" / "junk.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "map_index.json").unlink()
    assert [p["id"] for p in LocalStore(tmp_path).list_map_points()] == [jid]
    (tmp_path / "map_index.json").write_text("{broken", encoding="utf-8")
    assert [p["id"] for p in LocalStore(tmp_path).list_map_points()] == [jid]


def test_restart_sweep_updates_index(store):
    pending = store.create_job(BASE, b"x")
    store.mark_stale_pending_failed()
    assert pending["id"] not in {p["id"] for p in store.list_map_points()}  # server_restarted: no


def test_step_updates_do_not_rewrite_the_index(store, tmp_path):
    job = store.create_job(BASE, b"x")
    before = (tmp_path / "map_index.json").stat().st_mtime_ns
    store.update_job(job["id"], {"step": "detecting"})
    assert (tmp_path / "map_index.json").stat().st_mtime_ns == before


# --- Supabase, with a fake client (the real one has never been run: no credentials) -------------

class FakeQuery:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log
        self.calls = []

    def select(self, cols):
        self.calls.append(("select", cols)); return self

    def eq(self, col, val):
        self.calls.append(("eq", col, val)); return self

    @property
    def not_(self):
        self.calls.append(("not",)); return self

    def is_(self, col, val):
        self.calls.append(("is", col, val)); return self

    def order(self, col, desc=False):
        self.calls.append(("order", col, desc)); return self

    def limit(self, n):
        self.calls.append(("limit", n)); return self

    def execute(self):
        self.log.append(self.calls)
        data = []
        eqs = {c[1]: c[2] for c in self.calls if c[0] == "eq"}
        for r in self.rows:
            if eqs.get("status") == r["status"] and ("error->>code" not in eqs
                                                      or (r.get("error") or {}).get("code") == eqs["error->>code"]):
                if any(c[0] == "not" for c in self.calls) and r.get("score") is None:
                    continue
                data.append({k: v for k, v in r.items() if k != "status"})
        return type("Res", (), {"data": data})


class FakeClient:
    def __init__(self, rows):
        self.rows, self.log = rows, []

    def table(self, name):
        assert name == "measurements"
        return FakeQuery(self.rows, self.log)


def test_supabase_lists_with_narrow_queries():
    row = lambda i, status, **kw: {"id": i, "status": status, "created_at": f"2026-11-0{i}T00:00:00Z",
                                   "lat_rounded": 43.0, "lon_rounded": -78.79, "score": None,
                                   "confidence": None, "taken_at_utc": "t", "is_demo": False, **kw}
    rows = [
        row(1, "solved", score=5, confidence="high"),
        row(2, "failed", error=few_stars()),
        row(3, "failed", error={"code": "no_match"}),
        row(4, "solved"),
    ]
    store = SupabaseStore.__new__(SupabaseStore)
    store.client = FakeClient(rows)
    points = store.list_map_points(limit=10)
    assert [p["id"] for p in points] == [2, 1]  # newest first, failed one has no score
    assert points[0]["score"] is None and points[0]["confidence"] == "low"
    assert tuple(points[0]) == MAP_POINT_FIELDS
    for calls in store.client.log:  # never selects result, flags, image_url or error
        cols = [c[1] for c in calls if c[0] == "select"][0].split(",")
        assert not {"result", "flags", "image_url", "error"} & set(cols)
        assert ("limit", 10) in calls
