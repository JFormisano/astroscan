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

RESTART_ERROR = {
    "code": "server_restarted",
    "message": "The server restarted while your photo was being processed.",
    "next_step": "Please upload the photo again.",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def _job_file(self, job_id: str) -> Path:
        # job ids are our own uuid4 strings; reject anything else so a URL can't escape the dir
        uuid.UUID(job_id)
        return self.jobs_dir / f"{job_id}.json"

    def _write(self, job: dict) -> None:
        path = self._job_file(job["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job), encoding="utf-8")
        tmp.replace(path)  # atomic, so a poll never reads half a file

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
