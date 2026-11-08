"""Project the catalog onto a solved photo and mark ghosts. Owner: Person B.

Loaders read backend/data once and cache the lists. match_stars turns the
solver's WCS and detected sources into the overlay the results page draws.

Pixel convention, matching docs/solver-output.md and solver.fits_xy_to_image:
the returned WCS takes image pixels with astropy's origin=0. FITS pixel (1, 1)
is image pixel (0, 0). For JPEG/PNG solves, +y already points down the image,
so there is no vertical flip. all_world2pix / all_pix2world apply the SIP
distortion terms; wcs_world2pix does not.
"""

from __future__ import annotations

import json
import math
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# Stars farther out than this times the field's half-diagonal cannot land in
# the frame, and a SIP polynomial fitted on the photo diverges out there.
_FIELD_MARGIN = 1.5


@lru_cache(maxsize=1)
def load_stars():
    """Stars with visual magnitude <= 7. The Sun is not included."""
    return _load("stars.json")


@lru_cache(maxsize=1)
def load_constellations():
    """The 88 IAU stick figures, with segment endpoints in J2000 degrees."""
    return _load("constellation_lines.json")


def match_stars(wcs_header_or_path, image_width, image_height, sources_xy, match_radius_px=4.0):
    """Project catalog stars and constellation lines into one solved photo.

    wcs_header_or_path is the solver's `wcs` dict, a FITS header, a WCS, or a
    path to a .wcs/.fits file. sources_xy are image pixels ({x, y} or pairs),
    the same numbers solver.py puts in `sources`.

    Stars inside the frame are always returned. detected is false for ghost
    stars (no extracted source within match_radius_px). Each source is given
    to at most one star; the closer pair wins, and a tie goes to the brighter
    star. The dict is the overlay slice SkyOverlay and UnderTheHood read.
    """
    width = int(image_width)
    height = int(image_height)
    wcs = _load_wcs(wcs_header_or_path)
    catalog = load_stars()
    x, y, inside = _project_catalog(wcs, catalog, width, height)
    kept = np.flatnonzero(inside)
    detected = _assign_sources(
        x[kept], y[kept], np.array([catalog[int(i)]["mag"] for i in kept], dtype=float),
        _source_array(sources_xy), float(match_radius_px),
    )
    stars = []
    for index, is_detected in zip(kept, detected):
        star = catalog[int(index)]
        stars.append(
            {
                "id": star["id"],
                "hip": star["hip"],
                "name": star["proper"] or star["bayer_flamsteed"],
                "mag": star["mag"],
                "x": float(x[index]),
                "y": float(y[index]),
                "detected": bool(is_detected),
            }
        )
    field_width_deg, field_height_deg = _field_size_deg(wcs, width, height)
    expected = len(stars)
    return {
        "stars": stars,
        "constellations": _project_constellations(wcs, load_constellations(), width, height),
        "stats": {
            "stars_expected": expected,
            "stars_matched": int(np.count_nonzero(detected)) if expected else 0,
            # Same count. UnderTheHood labels this "Catalog stars in frame".
            "catalog_in_frame": expected,
            "field_width_deg": round(field_width_deg, 2),
            "field_height_deg": round(field_height_deg, 2),
            "match_radius_px": float(match_radius_px),
        },
    }


def _load(filename):
    path = _DATA_DIR / filename
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_wcs(wcs_header_or_path):
    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning

    if isinstance(wcs_header_or_path, WCS):
        return wcs_header_or_path
    if isinstance(wcs_header_or_path, (str, Path)):
        header = fits.getheader(wcs_header_or_path)
    elif isinstance(wcs_header_or_path, fits.Header):
        header = wcs_header_or_path
    elif isinstance(wcs_header_or_path, dict):
        header = fits.Header(wcs_header_or_path)
    else:
        raise TypeError("wcs_header_or_path must be a header dict, FITS header, WCS, or path")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FITSFixedWarning)
        return WCS(header)


def _sky_to_image(wcs, ra_deg, dec_deg):
    """J2000 degrees to image pixels (origin top-left, x right, y down).

    all_world2pix(..., 0) converts 1-based FITS pixels to 0-based image pixels.
    It does not flip y: the solver's JPEG/PNG WCS already points +y down.
    The SIP terms are applied here; wcs_world2pix would leave them out.

    A SIP fit only behaves near the photo. Catalog stars on the other side of
    the sky make the iteration diverge, and all_world2pix then raises. The
    catalog is limited to the field neighborhood before this call. Anything
    that still diverges comes back non-finite and the frame test drops it.
    """
    from astropy.wcs import NoConvergence

    # An all-NaN batch (every star diverged) warns inside the iteration.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        try:
            x, y = wcs.all_world2pix(ra_deg, dec_deg, 0)
        except NoConvergence as exc:
            solution = np.atleast_2d(np.asarray(exc.best_solution, dtype=float))
            x, y = solution[:, 0], solution[:, 1]
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def _image_to_sky(wcs, x, y):
    """Image pixels back to J2000 degrees. Inverse of _sky_to_image."""
    ra, dec = wcs.all_pix2world(x, y, 0)
    return np.asarray(ra, dtype=float), np.asarray(dec, dtype=float)


def _project_catalog(wcs, catalog, width, height):
    ra = np.array([star["ra_deg"] for star in catalog], dtype=float)
    dec = np.array([star["dec_deg"] for star in catalog], dtype=float)
    x = np.full(len(catalog), np.nan)
    y = np.full(len(catalog), np.nan)
    near = _near_field(wcs, ra, dec, width, height)
    if np.any(near):
        px, py = _sky_to_image(wcs, ra[near], dec[near])
        x[near] = np.ravel(px)
        y[near] = np.ravel(py)
    finite = np.isfinite(x) & np.isfinite(y)
    inside = finite & (x >= 0.0) & (x < width) & (y >= 0.0) & (y < height)
    return x, y, inside


def _near_field(wcs, ra_deg, dec_deg, width, height):
    """Catalog stars within 1.5× the field's angular half-diagonal.

    The half-diagonal is the sky angle from the field center (the center
    pixel) to the farther corner. Stars beyond the margin are left unprojected.
    """
    if len(ra_deg) == 0:
        return np.zeros(0, dtype=bool)
    from astropy.coordinates import SkyCoord

    center = _sky_coord(wcs, (width - 1) / 2.0, (height - 1) / 2.0)
    corners = _sky_coord(
        wcs,
        [-0.5, width - 0.5, -0.5, width - 0.5],
        [-0.5, -0.5, height - 0.5, height - 0.5],
    )
    half_diagonal = float(np.max(center.separation(corners).deg))
    stars = SkyCoord(np.asarray(ra_deg, dtype=float), np.asarray(dec_deg, dtype=float), unit="deg")
    return center.separation(stars).deg <= _FIELD_MARGIN * half_diagonal


def _sky_coord(wcs, x, y):
    from astropy.coordinates import SkyCoord

    ra, dec = _image_to_sky(wcs, x, y)
    return SkyCoord(ra, dec, unit="deg")


def _source_array(sources_xy):
    # A numpy array has no useful truth value; `if not sources_xy` raises.
    if sources_xy is None or len(sources_xy) == 0:
        return np.zeros((0, 2), dtype=float)
    rows = []
    for source in sources_xy:
        if isinstance(source, dict):
            rows.append((float(source["x"]), float(source["y"])))
        else:
            rows.append((float(source[0]), float(source[1])))
    return np.asarray(rows, dtype=float)


def _assign_sources(star_x, star_y, star_mag, sources, radius):
    """True where a source within radius was claimed. One source, one star."""
    matched = np.zeros(len(star_x), dtype=bool)
    if len(star_x) == 0 or len(sources) == 0:
        return matched
    distance = np.hypot(star_x[:, None] - sources[:, 0], star_y[:, None] - sources[:, 1])
    star_index, source_index = np.nonzero(distance <= radius)
    if len(star_index) == 0:
        return matched
    # Closer pair first. An equal distance goes to the brighter star.
    order = np.lexsort((star_mag[star_index], distance[star_index, source_index]))
    used_sources = np.zeros(len(sources), dtype=bool)
    for pair in order:
        star = int(star_index[pair])
        source = int(source_index[pair])
        if matched[star] or used_sources[source]:
            continue
        matched[star] = True
        used_sources[source] = True
    return matched


def _project_constellations(wcs, constellations, width, height):
    figures = []
    for constellation in constellations:
        segments = []
        in_frame = []
        seen = set()
        for start, end in constellation["lines"]:
            projected = [_vertex(wcs, start), _vertex(wcs, end)]
            if projected[0] is None or projected[1] is None:
                continue
            insides = [_inside(point, width, height) for point in projected]
            for (ra, dec), point, inside in zip((start, end), projected, insides):
                if not inside:
                    continue
                key = (round(float(ra), 6), round(float(dec), 6))
                if key not in seen:
                    seen.add(key)
                    in_frame.append(point)
            if insides[0] or insides[1]:
                (x1, y1), (x2, y2) = projected
                segments.append([x1, y1, x2, y2])
        if not in_frame:
            continue
        figures.append(
            {
                "name": constellation["name"],
                "label": {
                    "x": sum(point[0] for point in in_frame) / len(in_frame),
                    "y": sum(point[1] for point in in_frame) / len(in_frame),
                },
                "lines": segments,
            }
        )
    return figures


def _vertex(wcs, ra_dec):
    x, y = _sky_to_image(wcs, [ra_dec[0]], [ra_dec[1]])
    px, py = float(x[0]), float(y[0])
    if not (math.isfinite(px) and math.isfinite(py)):
        return None
    return px, py


def _inside(point, width, height):
    x, y = point
    return 0.0 <= x < width and 0.0 <= y < height


def _field_size_deg(wcs, image_w, image_h):
    """True angle between opposite edge midpoints, same measurement as solver.field_stats."""
    from astropy.coordinates import SkyCoord

    mid_x = (image_w - 1) / 2.0
    mid_y = (image_h - 1) / 2.0
    ra, dec = _image_to_sky(
        wcs,
        [-0.5, image_w - 0.5, mid_x, mid_x],
        [mid_y, mid_y, -0.5, image_h - 0.5],
    )
    sky = SkyCoord(ra, dec, unit="deg")
    width = float(sky[0].separation(sky[1]).deg)
    height = float(sky[2].separation(sky[3]).deg)
    return width, height
