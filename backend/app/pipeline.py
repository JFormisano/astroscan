"""From the solver's raw output to the result the results page draws. Owner: Person A.

`analyze()` runs after `solver.solve()` and adds what the screens need, using Person B's code:

    matching.match_stars       -> stars (with ghost flags), constellations, catalog stats
    conditions.evaluate_conditions -> Sun/Moon/horizon flags and planet positions

It only renames and projects; there is no new astronomy here. The result keeps everything the
solver returned (solver_used, wcs, sources, stats) so the under-the-hood view and any later
stage (scoring, AI) can use it, and gains the demo-cache shape (docs/solver-output.md):

    image {url, width, height} · taken_at_utc · location {lat, lon} · stars · constellations ·
    planets [{name, x, y, mag, ...}] · warnings [{type, ...}] · conditions · stats

No `score` yet: scoring.py (Person B) is not written. The page hides the score card without one.

Failure policy: a photo that SOLVED is never turned into a failed job because the extras broke.
If matching or conditions raise, the problem is logged and what we have is returned.
"""
import logging
import math
from collections.abc import Callable

import numpy as np

from app import conditions, matching

log = logging.getLogger(__name__)

STEP_MATCHING = "matching"  # one of the step keys Processing.jsx knows


def analyze(
    solver_result: dict,
    *,
    lat: float,
    lon: float,
    taken_at_utc: str,
    image_url: str | None = None,
    on_step: Callable[[str], None] | None = None,
) -> dict:
    """Return `solver_result` plus stars, constellations, planets and warnings. Never raises.

    `lat`/`lon` are the ~1 km rounded values and `taken_at_utc` an ISO 8601 string with a time zone
    (the job's stored values). A result without a WCS (the stub solver) is returned unchanged.
    """
    stats = solver_result.get("stats") or {}
    width, height = stats.get("image_width_px"), stats.get("image_height_px")
    if not (solver_result.get("wcs") and width and height):
        return solver_result
    if on_step:
        on_step(STEP_MATCHING)

    result = dict(solver_result)
    result["image"] = {"url": image_url, "width": width, "height": height}
    result["taken_at_utc"] = taken_at_utc
    result["location"] = {"lat": lat, "lon": lon}

    try:
        wcs = matching._load_wcs(solver_result["wcs"])
        overlay = matching.match_stars(wcs, width, height, solver_result.get("sources") or [])
    except Exception:
        log.exception("star matching failed; returning the solver output without star names")
        return result
    result["stars"] = overlay["stars"]
    result["constellations"] = overlay["constellations"]
    result["stats"] = _merge_stats(stats, overlay["stats"])

    try:
        cond = conditions.evaluate_conditions(
            lat, lon, taken_at_utc, ra_deg=stats.get("ra_center"), dec_deg=stats.get("dec_center")
        )
    except Exception:
        log.exception("condition checks failed; returning stars without warnings or planets")
        return result
    result["conditions"] = {k: v for k, v in cond.items() if k != "planets"}
    result["warnings"] = _warnings(cond)
    try:
        result["planets"] = _project_planets(cond.get("planets") or [], wcs, width, height)
    except Exception:
        log.exception("planet projection failed; returning without planets")
    return result


def _merge_stats(solver_stats: dict, match_stats: dict) -> dict:
    """One stats dict for the under-the-hood view.

    Both stages call their count `stars_matched` and mean different things: the solver's is how many
    detections its own pattern match used; matching's is how many catalog stars in the frame have a
    detection next to them. The page's "Matched to catalog" is the second, so that name goes to it
    and the solver's count is kept as `solver_stars_matched`.
    """
    merged = {**solver_stats, **match_stats}
    if "stars_matched" in solver_stats:
        merged["solver_stars_matched"] = solver_stats["stars_matched"]
    return merged


def _warnings(cond: dict) -> list[dict]:
    """Banner list in the demo shape, from B's flags (a rename, not a calculation)."""
    flags = cond.get("flags") or {}
    out = []
    if flags.get("twilight"):
        out.append({"type": "twilight"})
    if flags.get("moon_up"):
        out.append({"type": "moon", "moon_illumination_pct": round(cond.get("moon_illumination_pct") or 0)})
    if flags.get("low_altitude"):
        out.append({"type": "low_altitude"})
    return out


def _project_planets(planets: list[dict], wcs, width: int, height: int) -> list[dict]:
    """Planets above the horizon that fall inside the photo, as pixel positions.

    Uses the same SIP-aware projection and "near the field" guard as the catalog stars, so a planet
    far from the field can't land in the frame by polynomial divergence.
    """
    out = []
    for p in planets:
        if not p.get("above_horizon"):
            continue
        ra, dec = np.array([p["ra_deg"]], dtype=float), np.array([p["dec_deg"]], dtype=float)
        if not matching._near_field(wcs, ra, dec, width, height)[0]:
            continue
        x, y = (float(v[0]) for v in matching._sky_to_image(wcs, ra, dec))
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < width and 0 <= y < height):
            continue
        out.append(
            {
                "name": p["name"],
                "x": x,
                "y": y,
                "mag": p.get("magnitude"),
                "alt_deg": p.get("alt_deg"),
                "above_horizon": True,
            }
        )
    return out
