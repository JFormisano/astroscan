"""Light report storage. Owner: Person D (#9).

Mirrors Person A's pattern in app/db.py, kept separate so the two features don't share a file:

- LocalReportStore    JSON files + photos on disk under STORAGE_DIR/light_reports/. Used when
                      Supabase isn't configured (local dev, tests).
- SupabaseReportStore table `light_reports` + photos in the existing `images` bucket under
                      light-reports/ (see backend/supabase/light_reports.sql).

`get_report_store()` picks Supabase only when SUPABASE_URL and SUPABASE_SERVICE_KEY are both set.

A report is a dict: id, created_at, lat_rounded, lon_rounded, photo_url (EXIF-stripped copy or
None), category, controller, note, drafted_message, draft_source ("ai" | "template"),
measurement_id (or None). Only rounded coordinates are ever stored.
"""
import json
import os
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_id(report_id: str) -> bool:
    try:
        uuid.UUID(report_id)
        return True
    except ValueError:
        return False


class ReportStore(ABC):
    @abstractmethod
    def create(self, fields: dict, photo_bytes: bytes | None) -> dict:
        """Persist the (already stripped) photo, if any, and the report. Returns the stored report."""

    @abstractmethod
    def list(self) -> list[dict]:
        """All reports, newest first."""

    def photo_path(self, report_id: str) -> Path | None:
        """Local file for the stored photo, if this store keeps one (LocalReportStore only)."""
        return None


class LocalReportStore(ReportStore):
    def __init__(self, root: str | Path):
        self.dir = Path(root) / "light_reports"
        self.photos_dir = self.dir / "photos"
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, fields: dict, photo_bytes: bytes | None) -> dict:
        report_id = str(uuid.uuid4())
        photo_url = None
        if photo_bytes:
            (self.photos_dir / f"{report_id}.jpg").write_bytes(photo_bytes)
            photo_url = f"/api/light-reports/{report_id}/photo"
        report = {"id": report_id, "created_at": _now_iso(), "photo_url": photo_url, **fields}
        path = self.dir / f"{report_id}.json"
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(report), encoding="utf-8")
            tmp.replace(path)  # atomic, so a reader never sees half a file
        return report

    def list(self) -> list[dict]:
        reports = []
        for path in self.dir.glob("*.json"):
            try:
                reports.append(json.loads(path.read_text(encoding="utf-8")))
            except ValueError:
                continue  # skip a damaged file rather than break the map
        return sorted(reports, key=lambda r: r.get("created_at") or "", reverse=True)

    def photo_path(self, report_id: str) -> Path | None:
        if not _valid_id(report_id):
            return None
        path = self.photos_dir / f"{report_id}.jpg"
        return path if path.exists() else None


class SupabaseReportStore(ReportStore):
    """Needs backend/supabase/light_reports.sql applied (and the `images` bucket from schema.sql)."""

    TABLE = "light_reports"
    BUCKET = "images"
    PREFIX = "light-reports"

    def __init__(self, url: str, service_key: str):
        from supabase import create_client  # imported lazily so local dev needs no network deps

        self.client = create_client(url, service_key)

    def create(self, fields: dict, photo_bytes: bytes | None) -> dict:
        report_id = str(uuid.uuid4())
        photo_url = None
        if photo_bytes:
            bucket = self.client.storage.from_(self.BUCKET)
            path = f"{self.PREFIX}/{report_id}.jpg"
            bucket.upload(path, photo_bytes, {"content-type": "image/jpeg"})
            photo_url = bucket.get_public_url(path)
        row = {"id": report_id, "photo_url": photo_url, **fields}
        res = self.client.table(self.TABLE).insert(row).execute()
        return res.data[0]

    def list(self) -> list[dict]:
        res = self.client.table(self.TABLE).select("*").order("created_at", desc=True).execute()
        return res.data or []


_store: ReportStore | None = None


def get_report_store() -> ReportStore:
    """Process-wide store, chosen from env vars on first use. Also used as a FastAPI dependency."""
    global _store
    if _store is None:
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
        if url and key:
            _store = SupabaseReportStore(url, key)
        else:
            default_dir = Path(__file__).resolve().parent.parent / "storage"
            _store = LocalReportStore(os.environ.get("STORAGE_DIR") or default_dir)
    return _store
