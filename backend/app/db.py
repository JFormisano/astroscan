"""Job/measurement storage. Owner: Person A.

Job state lives here (never in server memory) so a restart or a second worker doesn't lose jobs.
Two implementations behind one small interface:

- LocalStore    JSON files + images on disk under STORAGE_DIR. Used when Supabase isn't configured.
- SupabaseStore Postgres table `measurements` + storage bucket `images` (see backend/supabase/schema.sql).

`get_store()` picks SupabaseStore only when SUPABASE_URL and SUPABASE_SERVICE_KEY are both set.
"""
import json
import os
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

INDEX_VERSION = 1

RESTART_ERROR = {
    "code": "server_restarted",
    "message": "The server restarted while your photo was being processed.",
    "next_step": "Please upload the photo again.",
}


MAP_LIMIT = 2000
# The only job fields that may leave the backend through /api/map.
MAP_POINT_FIELDS = ("id", "lat_rounded", "lon_rounded", "score", "confidence", "taken_at_utc", "is_demo")
FEW_STARS_CODE = "too_few_stars"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_point(row: dict) -> dict:
    """Project a job (or index entry) to the public map fields. Failed jobs have no score."""
    failed = row.get("status") == "failed"
    return {
        "id": row.get("id"),
        "lat_rounded": row.get("lat_rounded"),
        "lon_rounded": row.get("lon_rounded"),
        "score": None if failed else row.get("score"),
        "confidence": row.get("confidence") or ("low" if failed else None),
        "taken_at_utc": row.get("taken_at_utc"),
        "is_demo": bool(row.get("is_demo")),
    }


class Store(ABC):
    """A job is a dict. Fields: id, created_at, status (pending|solved|failed), step, taken_at_utc,
    lat_rounded, lon_rounded, flags, image_url, result, error, plus score/limiting_mag/pct_lost/
    confidence/solved/is_demo as later stages fill them in."""

    @abstractmethod
    def create_job(self, fields: dict, image_bytes: bytes) -> dict:
        """Persist the stripped image and a new pending job. Returns the stored job."""

    @abstractmethod
    def update_job(self, job_id: str, fields: dict) -> None: ...

    @abstractmethod
    def get_job(self, job_id: str) -> dict | None: ...

    @abstractmethod
    def mark_stale_pending_failed(self) -> int:
        """Called at startup: pending jobs from a previous process will never finish. Returns count."""

    @abstractmethod
    def list_map_points(self, limit: int = MAP_LIMIT) -> list[dict]:
        """Jobs that belong on the public map, newest first, as MAP_POINT_FIELDS dicts only.

        Included: solved jobs that have a score, and failed jobs whose error code is `too_few_stars`
        (reported with score None and confidence "low"; very few stars is itself evidence about the
        sky). Not included: pending jobs, solved jobs without a score yet, and other failures
        (timeouts, no_match, ...), which say nothing about the sky.

        This feeds a public endpoint, so it must never return result, flags, image_url or error.
        """

    def image_path(self, job_id: str) -> Path | None:
        """Local file for the stored image, if this store keeps one (LocalStore only)."""
        return None


class LocalStore(Store):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.jobs_dir = self.root / "jobs"
        self.images_dir = self.root / "images"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Small per-job summary so listing the map never parses the (large) result blobs.
        self._index_file = self.root / "map_index.json"
        self._index = self._load_index()

    def _job_file(self, job_id: str) -> Path:
        # job ids are our own uuid4 strings; reject anything else so a URL can't escape the dir
        uuid.UUID(job_id)
        return self.jobs_dir / f"{job_id}.json"

    @staticmethod
    def _index_entry(job: dict) -> dict:
        error = job.get("error")
        return {
            "id": job["id"],
            "created_at": job.get("created_at"),
            "status": job.get("status"),
            "error_code": error.get("code") if isinstance(error, dict) else None,
            "lat_rounded": job.get("lat_rounded"),
            "lon_rounded": job.get("lon_rounded"),
            "score": job.get("score"),
            "confidence": job.get("confidence"),
            "taken_at_utc": job.get("taken_at_utc"),
            "is_demo": bool(job.get("is_demo")),
        }

    def _load_index(self) -> dict:
        """Read map_index.json; if it is missing or damaged, rebuild it once from the job files."""
        try:
            data = json.loads(self._index_file.read_text(encoding="utf-8"))
            if data.get("version") == INDEX_VERSION and isinstance(data.get("jobs"), dict):
                return data["jobs"]
        except (FileNotFoundError, ValueError, AttributeError):
            pass
        index = {}
        for path in self.jobs_dir.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                index[job["id"]] = self._index_entry(job)
            except (ValueError, KeyError):
                continue  # skip a damaged file rather than break the map
        self._index = index
        self._save_index()
        return index

    def _save_index(self) -> None:
        tmp = self._index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": INDEX_VERSION, "jobs": self._index}), encoding="utf-8")
        tmp.replace(self._index_file)

    def _write(self, job: dict) -> None:
        path = self._job_file(job["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job), encoding="utf-8")
        tmp.replace(path)  # atomic, so a poll never reads half a file
        entry = self._index_entry(job)
        if self._index.get(job["id"]) != entry:  # step-only updates leave the index file alone
            self._index[job["id"]] = entry
            self._save_index()

    def create_job(self, fields: dict, image_bytes: bytes) -> dict:
        job_id = str(uuid.uuid4())
        (self.images_dir / f"{job_id}.jpg").write_bytes(image_bytes)
        job = {
            "id": job_id,
            "created_at": _now_iso(),
            "status": "pending",
            "step": None,
            "result": None,
            "error": None,
            "solved": False,
            "is_demo": False,
            "image_url": f"/api/measurements/{job_id}/image",
            **fields,
        }
        with self._lock:
            self._write(job)
        return job

    def update_job(self, job_id: str, fields: dict) -> None:
        with self._lock:
            job = self.get_job(job_id)
            if job is None:
                return
            job.update(fields)
            self._write(job)

    def get_job(self, job_id: str) -> dict | None:
        try:
            return json.loads(self._job_file(job_id).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):  # missing file or malformed id
            return None

    def mark_stale_pending_failed(self) -> int:
        count = 0
        with self._lock:
            for path in self.jobs_dir.glob("*.json"):
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("status") == "pending":
                    job.update(status="failed", step=None, error=RESTART_ERROR)
                    self._write(job)
                    count += 1
        return count

    def list_map_points(self, limit: int = MAP_LIMIT) -> list[dict]:
        with self._lock:
            entries = list(self._index.values())
        shown = [
            e
            for e in entries
            if (e["status"] == "solved" and e["score"] is not None)
            or (e["status"] == "failed" and e["error_code"] == FEW_STARS_CODE)
        ]
        shown.sort(key=lambda e: e.get("created_at") or "", reverse=True)
        return [_map_point(e) for e in shown[:limit]]

    def image_path(self, job_id: str) -> Path | None:
        try:
            uuid.UUID(job_id)
        except ValueError:
            return None
        path = self.images_dir / f"{job_id}.jpg"
        return path if path.exists() else None


class SupabaseStore(Store):
    """Needs the schema in backend/supabase/schema.sql applied and a public `images` bucket."""

    TABLE = "measurements"
    BUCKET = "images"

    def __init__(self, url: str, service_key: str):
        from supabase import create_client  # imported lazily so LocalStore needs no network deps

        self.client = create_client(url, service_key)

    def create_job(self, fields: dict, image_bytes: bytes) -> dict:
        job_id = str(uuid.uuid4())
        path = f"{job_id}.jpg"
        bucket = self.client.storage.from_(self.BUCKET)
        bucket.upload(path, image_bytes, {"content-type": "image/jpeg"})
        row = {
            "id": job_id,
            "status": "pending",
            "solved": False,
            "is_demo": False,
            "image_url": bucket.get_public_url(path),
            **fields,
        }
        res = self.client.table(self.TABLE).insert(row).execute()
        return res.data[0]

    def update_job(self, job_id: str, fields: dict) -> None:
        self.client.table(self.TABLE).update(fields).eq("id", job_id).execute()

    def get_job(self, job_id: str) -> dict | None:
        try:
            uuid.UUID(job_id)
        except ValueError:
            return None
        res = self.client.table(self.TABLE).select("*").eq("id", job_id).limit(1).execute()
        return res.data[0] if res.data else None

    def mark_stale_pending_failed(self) -> int:
        res = (
            self.client.table(self.TABLE)
            .update({"status": "failed", "step": None, "error": RESTART_ERROR})
            .eq("status", "pending")
            .execute()
        )
        return len(res.data or [])

    def list_map_points(self, limit: int = MAP_LIMIT) -> list[dict]:
        # Two plain queries (instead of one PostgREST `or` filter), each selecting only what the
        # map needs, so result/flags/image_url/error never leave the database.
        cols = "created_at," + ",".join(MAP_POINT_FIELDS)
        base = lambda: self.client.table(self.TABLE).select(cols)  # noqa: E731
        solved = (
            base().eq("status", "solved").not_.is_("score", "null")
            .order("created_at", desc=True).limit(limit).execute()
        )
        few_stars = (
            base().eq("status", "failed").eq("error->>code", FEW_STARS_CODE)
            .order("created_at", desc=True).limit(limit).execute()
        )
        rows = [{**r, "status": "solved"} for r in (solved.data or [])]
        rows += [{**r, "status": "failed"} for r in (few_stars.data or [])]
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return [_map_point(r) for r in rows[:limit]]


_store: Store | None = None


def get_store() -> Store:
    """Process-wide store, chosen from env vars on first use. Also used as a FastAPI dependency."""
    global _store
    if _store is None:
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
        if url and key:
            _store = SupabaseStore(url, key)
        else:
            default_dir = Path(__file__).resolve().parent.parent / "storage"
            _store = LocalStore(os.environ.get("STORAGE_DIR") or default_dir)
    return _store
