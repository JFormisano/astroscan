"""End-to-end smoke test against a running AstroScan, local or deployed.

    python scripts/smoke.py http://localhost:8080 ../test_photos/dunes_2048.jpg
    python scripts/smoke.py https://your-backend.onrender.com            # health check only
    python scripts/smoke.py http://localhost:8080 --blank                # expects a clean failure
    python scripts/smoke.py https://your-site.com --require-local        # fail if the real solver isn't in use

Checks, in order: /api/health answers (and how fast: the cold-start check), then, if a photo is
given, uploads it, follows the job's `step` values until it finishes, and prints the outcome.
Uses only the backend's own dependencies (httpx), so run it from backend/ with the venv active.
Exit code 0 = everything behaved as expected, 1 = something is wrong.
"""
import argparse
import io
import sys
import time
from pathlib import Path

import httpx


def blank_photo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), (8, 8, 12)).save(buf, format="JPEG")
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url", help="origin only, e.g. http://localhost:8080 or https://api.example.com")
    ap.add_argument("photo", nargs="?", help="JPEG/PNG to upload (omit for a health check only)")
    ap.add_argument("--blank", action="store_true", help="upload a blank sky and expect a clean 'failed' result")
    ap.add_argument("--require-local", action="store_true",
                    help="fail unless the server reports it will use the real local solve-field")
    ap.add_argument("--insecure", action="store_true",
                    help="skip TLS certificate checks (only for a local test with a self-signed certificate)")
    ap.add_argument("--timeout", type=float, default=300, help="seconds to wait for the job (default 300)")
    ap.add_argument("--lat", default="43.0008")
    ap.add_argument("--lon", default="-78.7897")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    client = httpx.Client(timeout=60, follow_redirects=True, verify=not args.insecure)

    t0 = time.monotonic()
    try:
        health = client.get(f"{base}/api/health")
        health.raise_for_status()
    except httpx.HTTPError as e:
        print(f"FAIL  /api/health did not answer: {e}")
        return 1
    info = health.json().get("solver", {})
    print(f"ok    /api/health in {time.monotonic() - t0:.1f}s  status={health.json().get('status')} solver={info}")
    if args.require_local and info.get("using") != "local":
        print(f"FAIL  --require-local: this server would use {info.get('using')!r}, not the real solve-field "
              f"(local_available={info.get('local_available')}, index_files={info.get('index_files')})")
        return 1

    if not args.photo and not args.blank:
        return 0

    if args.blank:
        name, data = "blank.jpg", blank_photo()
    else:
        path = Path(args.photo)
        name, data = path.name, path.read_bytes()
    res = client.post(
        f"{base}/api/measurements",
        files={"image": (name, data, "image/jpeg")},
        data={"lat": args.lat, "lon": args.lon, "taken_at": "2026-11-08T02:30:05Z"},
    )
    if res.status_code != 201:
        print(f"FAIL  upload rejected ({res.status_code}): {res.text[:300]}")
        return 1
    job_id = res.json()["job_id"]
    print(f"ok    uploaded {name} ({len(data) / 1024:.0f} KB) -> job {job_id}")

    start, last = time.monotonic(), None
    while time.monotonic() - start < args.timeout:
        job = client.get(f"{base}/api/measurements/{job_id}").json()
        state = (job["status"], job.get("step"))
        if state != last:
            print(f"      {time.monotonic() - start:5.0f}s  status={job['status']} step={job.get('step')}")
            last = state
        if job["status"] != "pending":
            break
        time.sleep(2)
    else:
        print(f"FAIL  still pending after {args.timeout:.0f}s")
        return 1

    elapsed = time.monotonic() - start
    if job["status"] == "solved":
        stats = (job.get("result") or {}).get("stats", {})
        print(
            f"ok    solved in {elapsed:.0f}s by {job['result'].get('solver_used')}: "
            f"{stats.get('stars_matched')} stars matched, field {stats.get('field_width_deg')} x "
            f"{stats.get('field_height_deg')} deg"
        )
        if args.blank:
            print("FAIL  a blank sky should not solve")
            return 1
        return 0

    err = job.get("error") or {}
    print(f"      failed: {err.get('code')} | {err.get('message')} | {err.get('next_step')}")
    if args.blank and err.get("code") == "too_few_stars" and err.get("message") and err.get("next_step"):
        print(f"ok    blank sky failed cleanly in {elapsed:.0f}s with a plain message and next step")
        return 0
    print("FAIL  the job failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
