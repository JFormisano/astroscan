"""Download one nova.astrometry.net job into tests/fixtures. Dev tool only.

The app never imports this. From backend/:

    .venv/bin/python scripts/fetch_fixtures.py JOB_ID --submission SUB_ID

wcs.fits, axy.fits and corr.fits are the URLs in the current API docs
(https://astrometry.net/doc/net/api.html, "Getting job results: results files"),
which match net/urls.py:

    {base}/wcs_file/{job_id}
    {base}/axy_file/{job_id}
    {base}/corr_file/{job_id}

solver.py fetches those same paths. Its download helper is nested inside
_solve_nova, so it cannot be called on its own. This script uses
app.solver._nova_base() and the same "{base}/{kind}/{job_id}" path.

The original upload is not one of those job-file URLs. In
net/views/image.py the results page calls serve_image (urls.py path
/image/{id}) the original, and that id is the "images" list on
GET {base}/api/submissions/{sub_id}. Job info does not include it, so
pass the submission id from the upload response or the /status/SUB_ID page.

Current api_help blocks programmatic downloads unless the request sends:

    Referer: https://nova.astrometry.net/api/login
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.solver import _nova_base

_FIXTURES = _BACKEND / "tests" / "fixtures"
_REFERER = "https://nova.astrometry.net/api/login"
_JOB_FILES = (
    ("wcs_file", "wcs.fits"),
    ("axy_file", "axy.fits"),
    ("corr_file", "corr.fits"),
)


def main():
    args = _parse_args()
    base = _nova_base()
    out_dir = _FIXTURES / str(args.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        timeout=httpx.Timeout(30.0, read=120.0),
        headers={"Referer": _REFERER},
        follow_redirects=True,
    ) as client:
        info = _get_json(client, f"{base}/api/jobs/{args.job_id}/info/")
        if info.get("status") != "success":
            raise SystemExit(f"job {args.job_id} is not a successful solve: {info.get('status')!r}")

        written = []
        for kind, name in _JOB_FILES:
            path = out_dir / name
            _download(client, f"{base}/{kind}/{args.job_id}", path)
            written.append(path)

        submission = _get_json(client, f"{base}/api/submissions/{args.submission}")
        image_id = _image_id_for_job(submission, args.job_id, args.submission)
        image_name = _safe_name(info.get("original_filename") or f"image_{image_id}")
        image_path = out_dir / image_name
        _download(client, f"{base}/image/{image_id}", image_path)
        written.append(image_path)

    for path in written:
        print(path)


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id", type=int, help="nova.astrometry.net job id")
    parser.add_argument(
        "--submission",
        required=True,
        type=int,
        help="submission id that produced this job; its JSON 'images' list is the original",
    )
    return parser.parse_args()


def _get_json(client: httpx.Client, url: str) -> dict:
    res = client.get(url)
    if res.status_code == 404:
        raise SystemExit(f"nova has no {url} (private jobs are hidden without a session)")
    res.raise_for_status()
    body = res.json()
    if not isinstance(body, dict):
        raise SystemExit(f"unexpected response from {url}")
    return body


def _download(client: httpx.Client, url: str, path: Path) -> None:
    with client.stream("GET", url) as res:
        if res.status_code == 404:
            raise SystemExit(f"nova has no {url}")
        res.raise_for_status()
        content_type = (res.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type.startswith("text/html"):
            raise SystemExit(f"{url} returned HTML, not the file. The Referer header was refused.")
        tmp = path.with_suffix(path.suffix + ".part")
        with tmp.open("wb") as handle:
            for chunk in res.iter_bytes():
                handle.write(chunk)
        tmp.replace(path)


def _image_id_for_job(submission: dict, job_id: int, submission_id: int) -> int:
    jobs = submission.get("jobs") or []
    images = submission.get("images") or []
    if job_id not in jobs:
        raise SystemExit(f"job {job_id} is not in submission {submission_id} (jobs={jobs})")
    if len(jobs) != len(images):
        raise SystemExit(
            f"submission {submission_id} lists {len(jobs)} jobs and {len(images)} images; "
            "cannot tell which image this job solved"
        )
    image_id = images[jobs.index(job_id)]
    if not isinstance(image_id, int):
        raise SystemExit(f"submission {submission_id} image id is {image_id!r}, expected an int")
    return image_id


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(name).name)
    return cleaned or "image"


if __name__ == "__main__":
    main()
