"""Plate solving. Owner: Person A.

`solve()` turns one stripped photo into a WCS solution plus the stars the solver detected.
Two solvers sit behind it and nothing outside this file knows which one ran:

- local    `solve-field` from astrometry.net (primary; wide-field 4100-series index files)
- nova     the public nova.astrometry.net API (fallback)

SOLVER_MODE picks the strategy: auto (default) | local | api | stub.
  auto   local if `solve-field` and its index files are present; if local is unavailable or
         crashes, fall back to the API. A local run that finishes with no match fails fast
         (no API retry, which could mean a surprise multi-minute wait).
  stub   the old placeholder, for tests and frontend development.

Pixel conventions (CLAUDE.md section 5): everything returned in `sources` is in IMAGE pixels
(origin top-left, x right, y down, pixel centres on integers). astrometry.net numbers the pixels
of a JPEG the same way but starting at 1 (FITS style), and its y axis points DOWN for JPEG/PNG
input (checked against real photos: detected stars sit on bright pixels only without a y flip).
So the returned WCS takes image pixels directly with astropy's origin=0 API:
`WCS(header).all_pix2world(x, y, 0)`. docs/solver-output.md has the details.
"""
import io
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image

log = logging.getLogger(__name__)

STUB_DELAY_S = 2.0  # stub mode only: pretend the solve takes a moment; tests set this to 0

# Step keys the Processing page understands (frontend/src/pages/Processing.jsx).
STEP_DETECTING = "detecting"
STEP_SOLVING = "solving"

# Accept a solve only with real evidence (CLAUDE.md section 4: "don't trust the exit code alone").
MIN_DETECTED_STARS = 12
MIN_MATCHED_STARS = 8
MAX_OBJS = 2000  # solve-field keeps the brightest N detections: the engine's verify step is ~3x
# slower on 7000+ mostly-noise detections with identical matches (measured), yet faint stars matter
# for ghost-star detection, so keep plenty.
MAX_SOURCES_RETURNED = 1000  # brightest first; keeps the job JSON small

# One local solve at a time on this machine (CLAUDE.md section 3). Waiting jobs stay `pending`.
# Held only around the local solve-field run; API polling is network-bound and needs no lock.
_local_lock = threading.Lock()


# --- errors -------------------------------------------------------------------------------


class SolveFailed(Exception):
    """Raised when the photo can't be solved. Becomes the job's `error`.

    Codes: too_few_stars, no_match, solve_timeout, solver_unavailable, solve_failed.
    """

    def __init__(self, message: str, next_step: str = "", detected_stars: int | None = None, code: str = "solve_failed"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_step = next_step
        self.detected_stars = detected_stars


_BETTER_PHOTO = "Take the photo with your phone's Night mode, away from bright lights, holding it steady, then upload it again."


def too_few_stars(detected: int | None) -> SolveFailed:
    return SolveFailed(
        "Too few stars to identify.",
        "Very few visible stars is itself a sign of heavy light pollution (or cloud). "
        + _BETTER_PHOTO
        + " You can still add this spot to the map.",
        detected_stars=detected,
        code="too_few_stars",
    )


def no_match(detected: int | None) -> SolveFailed:
    return SolveFailed(
        "We couldn't match this photo to known stars.",
        "The sky may be cloudy, blurry or mostly trees and buildings. " + _BETTER_PHOTO,
        detected_stars=detected,
        code="no_match",
    )


def solve_timeout(detected: int | None) -> SolveFailed:
    return SolveFailed(
        "Matching the stars took too long, so we stopped.",
        "Try again, or use a photo with more stars showing. " + _BETTER_PHOTO,
        detected_stars=detected,
        code="solve_timeout",
    )


def solver_unavailable() -> SolveFailed:
    return SolveFailed(
        "Our star-matching service isn't available right now.",
        "Please try again in a few minutes, or try a sample photo.",
        code="solver_unavailable",
    )


def solve_error() -> SolveFailed:
    return SolveFailed(
        "We couldn't finish matching the stars in this photo.",
        "Please try again. If it keeps happening, try a different photo.",
        code="solve_failed",
    )


# --- settings -----------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def local_timeout_s() -> float:
    return _env_float("LOCAL_SOLVE_TIMEOUT_S", 90)


def api_timeout_s() -> float:
    return _env_float("API_SOLVE_TIMEOUT_S", 240)


def index_dir() -> Path:
    return Path(os.environ.get("ASTROMETRY_INDEX_DIR") or "/data/index")


# --- pure helpers (unit-tested) -----------------------------------------------------------

# Phone photos: the saved image is often cropped, so EXIF focal lengths over-state the field.
# Search 0.35x to 1.2x of the EXIF estimate (CLAUDE.md section 4). No EXIF: wide fallback.
SCALE_LOW_FACTOR, SCALE_HIGH_FACTOR = 0.35, 1.2
FALLBACK_SCALE_DEG = (10.0, 100.0)
MIN_SCALE_DEG, MAX_SCALE_DEG = 2.0, 120.0


def scale_range_deg(image_w: int, image_h: int, focal_35mm: float | None) -> tuple[float, float]:
    """(low, high) width of the photo's x axis in degrees, for the solver's scale hint.

    A 35mm-equivalent focal length f spans 36 mm across the long side and 24 mm across the short
    side, so the angular width of the x axis is 2*atan(S / (2f)) with S = 36 for landscape and
    24 for portrait.
    """
    if not focal_35mm or focal_35mm <= 0:
        return FALLBACK_SCALE_DEG
    sensor_mm = 36.0 if image_w >= image_h else 24.0
    width_deg = math.degrees(2 * math.atan(sensor_mm / (2 * focal_35mm)))
    low = max(MIN_SCALE_DEG, width_deg * SCALE_LOW_FACTOR)
    high = min(MAX_SCALE_DEG, width_deg * SCALE_HIGH_FACTOR)
    return (low, high) if low < high else FALLBACK_SCALE_DEG


def fits_xy_to_image(x_fits: float, y_fits: float) -> tuple[float, float]:
    """astrometry.net pixel numbers -> image pixels.

    astrometry.net counts pixels from 1 (FITS style); image pixels count from 0. For JPEG/PNG input
    its y axis points down like the image's, so there is NO vertical flip here (a flip would
    mirror every label; tests/test_solver.py and the Docker run check this on real photos).
    """
    return x_fits - 1.0, y_fits - 1.0


def image_xy_to_fits(x: float, y: float) -> tuple[float, float]:
    """Inverse of fits_xy_to_image, for code that follows the 1-based FITS WCS convention."""
    return x + 1.0, y + 1.0


def _clean_value(value):
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    try:
        return value.item()  # numpy scalar
    except AttributeError:
        return str(value)


def header_to_dict(header) -> dict:
    """FITS header -> plain dict (JSON-safe). Drops COMMENT/HISTORY/blank cards."""
    return {k: _clean_value(header[k]) for k in header if k and k not in ("COMMENT", "HISTORY")}


def sources_from_axy(axy_hdul) -> list[dict]:
    """Detected stars from an astrometry.net .axy file, brightest first, in image pixels."""
    data = axy_hdul[1].data
    cols = {c.upper(): c for c in data.columns.names}
    xs, ys = data[cols["X"]], data[cols["Y"]]
    flux = data[cols["FLUX"]] if "FLUX" in cols else [0.0] * len(xs)
    out = []
    for x_fits, y_fits, f in zip(xs, ys, flux):
        x, y = fits_xy_to_image(float(x_fits), float(y_fits))
        out.append({"x": round(x, 2), "y": round(y, 2), "flux": round(float(f), 2)})
    out.sort(key=lambda s: -s["flux"])
    return out


def field_stats(header, image_w: int, image_h: int) -> dict:
    """Field size, centre and pixel scale from a solved WCS header."""
    from astropy.coordinates import SkyCoord
    from astropy.wcs import WCS, FITSFixedWarning
    from astropy.wcs.utils import proj_plane_pixel_scales

    with warnings.catch_warnings():
        # "more axes than the image": we build the WCS from a bare header, so there is no image.
        warnings.simplefilter("ignore", FITSFixedWarning)
        wcs = WCS(header)
    # Image pixels (= astropy origin=0 pixels): edge midpoints and the centre.
    mid_x, mid_y = (image_w - 1) / 2, (image_h - 1) / 2
    pts = [(-0.5, mid_y), (image_w - 0.5, mid_y), (mid_x, -0.5), (mid_x, image_h - 0.5), (mid_x, mid_y)]
    sky = wcs.pixel_to_world(*zip(*pts))
    width = SkyCoord(sky[0]).separation(SkyCoord(sky[1])).deg  # true angle on the sky, not flat-grid
    height = SkyCoord(sky[2]).separation(SkyCoord(sky[3])).deg
    scale_arcsec = float(proj_plane_pixel_scales(wcs).mean()) * 3600  # at the reference point
    return {
        "field_width_deg": round(float(width), 2),
        "field_height_deg": round(float(height), 2),
        "ra_center": round(float(sky[4].ra.deg), 4),
        "dec_center": round(float(sky[4].dec.deg), 4),
        "pixel_scale_arcsec": round(scale_arcsec, 2),
    }


# --- solver output ------------------------------------------------------------------------


@dataclass
class SolveOutput:
    """What either solver produces. `to_result()` is the 'raw solver block' (docs/solver-output.md)."""

    solver_used: str
    wcs: dict
    sources: list[dict]
    image_w: int
    image_h: int
    stars_detected: int
    stars_matched: int | None
    stats: dict = field(default_factory=dict)

    def to_result(self, solve_seconds: float) -> dict:
        return {
            "solver_used": self.solver_used,
            "wcs": self.wcs,
            "sources": self.sources[:MAX_SOURCES_RETURNED],
            "stats": {
                "image_width_px": self.image_w,
                "image_height_px": self.image_h,
                "stars_detected": self.stars_detected,
                "stars_matched": self.stars_matched,
                **self.stats,
                "solve_seconds": round(solve_seconds, 2),
            },
        }


def build_output(
    solver_used: str,
    header,
    axy_hdul,
    image_w: int,
    image_h: int,
    stars_matched: int | None,
) -> SolveOutput:
    sources = sources_from_axy(axy_hdul)
    return SolveOutput(
        solver_used=solver_used,
        wcs=header_to_dict(header),
        sources=sources,
        image_w=image_w,
        image_h=image_h,
        stars_detected=len(sources),
        stars_matched=stars_matched,
        stats=field_stats(header, image_w, image_h),
    )


# --- nova.astrometry.net (fallback) -------------------------------------------------------

NOVA_URL = "https://nova.astrometry.net"
_NOVA_POLL_S = 5.0


def _nova_base() -> str:
    return (os.environ.get("ASTROMETRY_API_URL") or NOVA_URL).rstrip("/")


def _nova_json(res: httpx.Response) -> dict:
    res.raise_for_status()
    body = res.json()
    if not isinstance(body, dict):
        raise ValueError("unexpected API response")
    return body


def _solve_nova(
    image_path: Path,
    image_w: int,
    image_h: int,
    scale: tuple[float, float],
    step: Callable[[str], None],
    *,
    http: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> SolveOutput:
    """Solve through nova.astrometry.net. Slow (minutes), so it has its own hard time limit."""
    from astropy.io import fits

    api_key = os.environ.get("ASTROMETRY_API_KEY")
    if not api_key:
        log.warning("ASTROMETRY_API_KEY not set; the public API fallback is unavailable")
        raise solver_unavailable()

    own_client = http is None
    client = http or httpx.Client(timeout=httpx.Timeout(30.0, read=60.0))
    base = _nova_base()
    deadline = time.monotonic() + api_timeout_s()
    try:
        step(STEP_DETECTING)
        login = _nova_json(client.post(f"{base}/api/login", data={"request-json": json.dumps({"apikey": api_key})}))
        if login.get("status") != "success" or not login.get("session"):
            log.error("nova login failed: %s", login.get("errormessage") or login.get("message"))
            raise solver_unavailable()
        session = login["session"]

        params = {
            "session": session,
            "publicly_visible": "n",  # public submissions are viewable by anyone (privacy)
            "scale_units": "degwidth",
            "scale_type": "ul",
            "scale_lower": round(scale[0], 2),
            "scale_upper": round(scale[1], 2),
            "tweak_order": 3,  # SIP distortion terms (phone lenses)
            "crpix_center": True,
        }
        upload = _nova_json(
            client.post(
                f"{base}/api/upload",
                data={"request-json": json.dumps(params)},
                files={"file": (image_path.name, image_path.read_bytes(), "application/octet-stream")},
            )
        )
        if upload.get("status") != "success" or "subid" not in upload:
            log.error("nova upload failed: %s", upload)
            raise solve_error()
        subid = upload["subid"]

        step(STEP_SOLVING)
        job_id = None
        while True:
            if time.monotonic() > deadline:
                raise solve_timeout(None)
            sub = _nova_json(client.get(f"{base}/api/submissions/{subid}"))
            job_id = next((j for j in sub.get("jobs") or [] if j), None)  # jobs may hold None while queued
            if job_id is not None:
                job = _nova_json(client.get(f"{base}/api/jobs/{job_id}"))
                status = job.get("status")
                if status == "success":
                    break
                if status == "failure":
                    raise no_match(None)
            sleep(_NOVA_POLL_S)

        def fetch(kind: str) -> bytes:
            res = client.get(f"{base}/{kind}/{job_id}")
            res.raise_for_status()
            return res.content

        header = fits.getheader(io.BytesIO(fetch("wcs_file")))
        with fits.open(io.BytesIO(fetch("axy_file"))) as axy:
            matched = None
            try:
                with fits.open(io.BytesIO(fetch("corr_file"))) as corr:
                    matched = len(corr[1].data)
            except Exception:  # the matched count is a bonus; the solve itself is fine
                log.info("could not read nova corr file", exc_info=True)
            out = build_output("nova", header, axy, image_w, image_h, matched)
        if out.stars_matched is not None and out.stars_matched < MIN_MATCHED_STARS:
            raise no_match(out.stars_detected)
        return out
    except SolveFailed:
        raise
    except (httpx.HTTPError, ValueError, KeyError, OSError):
        log.exception("nova solve failed")
        raise solve_error() from None
    finally:
        if own_client:
            client.close()


# --- local solve-field (primary) ----------------------------------------------------------

MIN_LOG_ODDS = 30.0  # solve-field itself accepts at ~20.7 (odds 1e9); we want clearly more
AUGMENT_TIMEOUT_S = 40  # star extraction on a <=2048 px photo takes 1-9 s


class LocalSolverUnavailable(Exception):
    """solve-field isn't installed, has no index files, or crashed. Internal: triggers the API fallback."""


def _config_args(flag: str = "--config") -> list[str]:
    cfg = os.environ.get("ASTROMETRY_CONFIG")
    return [flag, cfg] if cfg else []


def local_available() -> bool:
    """True if solve-field, astrometry-engine and at least one index file are present."""
    return bool(
        shutil.which("solve-field")
        and shutil.which("astrometry-engine")
        and any(index_dir().glob("index-*.fits"))
    )


def _run(cmd: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    """Run a command, return (exit code, combined output). On timeout kill it and its children
    (solve-field starts helper programs) and raise subprocess.TimeoutExpired."""
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,  # own process group, so we can kill the whole tree
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except (AttributeError, ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        raise
    return proc.returncode, out or ""


def _solve_local(
    image_path: Path,
    image_w: int,
    image_h: int,
    scale: tuple[float, float],
    step: Callable[[str], None],
) -> SolveOutput:
    """Two stages, the same ones solve-field runs internally, so we can look in between:
    1. `solve-field --just-augment`  extracts stars (about a second or few) and writes an .axy file.
       Too few stars -> fail right here instead of searching until a timeout.
    2. `astrometry-engine`           matches star patterns against the index files and writes the WCS.
    `solve-field` exits 0 even when it didn't solve, so success = the .solved file AND enough
    matched stars AND a high match log-odds.
    """
    from astropy.io import fits

    limit = local_timeout_s()
    with _local_lock, tempfile.TemporaryDirectory(prefix="solve-") as tmp:
        work = Path(tmp)
        axy_path = work / "photo.axy"
        step(STEP_DETECTING)
        augment = [
            "solve-field", *_config_args(), "--just-augment", "--no-plots", "--overwrite",
            "--dir", str(work), "--out", "photo", "--axy", str(axy_path),
            "--scale-units", "degwidth",
            "--scale-low", f"{scale[0]:.2f}", "--scale-high", f"{scale[1]:.2f}",
            "--tweak-order", "3",  # SIP distortion terms: phone lenses bend the edges
            "--crpix-center",
            "--objs", str(MAX_OBJS),
            "--cpulimit", str(int(limit)),
            str(image_path),
        ]  # fmt: skip
        try:
            rc, out = _run(augment, work, AUGMENT_TIMEOUT_S)
        except FileNotFoundError:
            raise LocalSolverUnavailable("solve-field not installed") from None
        except subprocess.TimeoutExpired:
            raise LocalSolverUnavailable("star extraction hung") from None
        if rc != 0 or not axy_path.exists():
            raise LocalSolverUnavailable(f"solve-field --just-augment failed (exit {rc}): {out[-500:]}")
        with fits.open(axy_path, memmap=False) as axy:
            detected = len(axy[1].data) if len(axy) > 1 else 0
        if detected < MIN_DETECTED_STARS:
            raise too_few_stars(detected)

        step(STEP_SOLVING)
        engine = ["astrometry-engine", *_config_args("-c"), str(axy_path)]  # the engine spells it -c
        try:
            rc, out = _run(engine, work, limit)  # wall-clock limit; --cpulimit inside the .axy covers CPU time
        except FileNotFoundError:
            raise LocalSolverUnavailable("astrometry-engine not installed") from None
        except subprocess.TimeoutExpired:
            raise solve_timeout(detected) from None
        solved = (work / "photo.solved").exists()
        if not solved:
            if "CPU time limit reached" in out:
                raise solve_timeout(detected)
            if rc != 0:
                raise LocalSolverUnavailable(f"astrometry-engine failed (exit {rc}): {out[-500:]}")
            raise no_match(detected)

        with fits.open(work / "photo.corr", memmap=False) as corr:
            matched = len(corr[1].data)
        log_odds = None
        try:
            with fits.open(work / "photo.match", memmap=False) as match:
                log_odds = float(match[1].data["LOGODDS"][0])
        except Exception:  # the check is a bonus; the matched-star count above is the main guard
            log.info("could not read match log-odds", exc_info=True)
        if matched < MIN_MATCHED_STARS or (log_odds is not None and log_odds < MIN_LOG_ODDS):
            log.info("rejecting weak solve: matched=%s log_odds=%s", matched, log_odds)
            raise no_match(detected)

        header = fits.getheader(work / "photo.wcs")
        with fits.open(axy_path, memmap=False) as axy:
            out_ = build_output("local", header, axy, image_w, image_h, matched)
        if log_odds is not None:
            out_.stats["log_odds"] = round(log_odds, 1)
        return out_


# --- the entry point ----------------------------------------------------------------------


def _stub_result(step: Callable[[str], None]) -> dict:
    step(STEP_DETECTING)
    time.sleep(STUB_DELAY_S / 2)
    step(STEP_SOLVING)
    time.sleep(STUB_DELAY_S / 2)
    return {
        "stub": True,
        "note": "Placeholder result from the stub solver (SOLVER_MODE=stub).",
        "solver_used": "stub",
    }


def solve(
    image_path: Path,
    lat: float,
    lon: float,
    taken_at: datetime,
    on_step: Callable[[str], None] | None = None,
    hints: dict | None = None,
) -> dict:
    """Solve one stripped photo. `lat`/`lon` are the ~1 km rounded values; `taken_at` is UTC.

    `hints` is the job's `flags` (we use `focal_35mm`). Calls `on_step(key)` with 'detecting' then
    'solving' so the Processing page can show progress. Returns the raw solver block
    (docs/solver-output.md) or raises SolveFailed. Location and time are not needed to solve
    (the solve is blind) and are not sent to any solver.
    """
    step = on_step or (lambda _s: None)
    mode = (os.environ.get("SOLVER_MODE") or "auto").strip().lower()
    if mode == "stub":
        return _stub_result(step)

    with Image.open(image_path) as img:
        image_w, image_h = img.size
    scale = scale_range_deg(image_w, image_h, (hints or {}).get("focal_35mm"))
    t0 = time.monotonic()

    if mode == "api":
        out = _solve_nova(image_path, image_w, image_h, scale, step)
    elif mode == "local":
        try:
            out = _solve_local(image_path, image_w, image_h, scale, step)
        except LocalSolverUnavailable:
            log.exception("local solver unavailable (SOLVER_MODE=local)")
            raise solver_unavailable() from None
    else:  # auto
        out = None
        if local_available():
            try:
                out = _solve_local(image_path, image_w, image_h, scale, step)
            except LocalSolverUnavailable:
                log.exception("local solver failed; falling back to the public API")
        else:
            log.warning("solve-field or its index files not found; using the public API")
        if out is None:
            out = _solve_nova(image_path, image_w, image_h, scale, step)
    return out.to_result(time.monotonic() - t0)
