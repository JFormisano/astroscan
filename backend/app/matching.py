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
# A source this close to a catalog star is that star. Phone solves land a
# median of 1–2 px off, and 10–15 px at the edges, so the strict radius is
# wider than the old 4 px. Only stars of magnitude _BRIGHT_MAG or brighter
# may claim a source out to _BRIGHT_RADIUS_PX, and only when that star is
# the closest catalog star to the source.
_MATCH_RADIUS_PX = 8.0
_BRIGHT_RADIUS_PX = 16.0
_BRIGHT_MAG = 3.5
# Mizar's catalog companion is 19 arcsec away: the same pixel on a phone
# photo. The fainter member would otherwise take the detection. Alcor, at
# about 12 arcmin, stays a separate star.
_COMPANION_ARCSEC = 60.0
# Annulus outside the star core. A median this bright is ground or a
# building, not sky. Dark water stays for the horizon cut.
_ANNULUS_INNER_PX = 8
_ANNULUS_OUTER_PX = 18
_FOREGROUND_LUMA = 110.0


@lru_cache(maxsize=1)
def load_stars():
    """Stars with visual magnitude <= 7. The Sun is not included."""
    return _load("stars.json")


@lru_cache(maxsize=1)
def load_constellations():
    """The 88 IAU stick figures, with segment endpoints in J2000 degrees."""
    return _load("constellation_lines.json")


def match_stars(
    wcs_header_or_path,
    image_width,
    image_height,
    sources_xy,
    match_radius_px=_MATCH_RADIUS_PX,
    *,
    lat=None,
    lon=None,
    taken_at=None,
    image=None,
):
    """Project catalog stars and constellation lines into one solved photo.

    wcs_header_or_path is the solver's `wcs` dict, a FITS header, a WCS, or a
    path to a .wcs/.fits file. sources_xy are image pixels ({x, y} or pairs),
    the same numbers solver.py puts in `sources`.

    Stars on the sky and inside the frame are returned. detected is false for
    ghost stars. Each source is given to at most one star; the closer pair
    wins, and a tie goes to the brighter star. Stars of magnitude 3.5 or
    brighter may still claim a source out to 16 px when they are the closest
    catalog star to it.

    lat, lon (degrees) and taken_at (timezone-aware ISO 8601) must be passed
    together. Stars at or below the geometric horizon are left out, and so
    are constellation lines that cross it, so the ghost toggle does not draw
    catalog stars onto the ground. image is a path or an RGB array; a star
    whose surrounding pixels are bright foreground is left out too.
    """
    width = int(image_width)
    height = int(image_height)
    observer = _observer(lat, lon, taken_at)
    wcs = _load_wcs(wcs_header_or_path)
    catalog = load_stars()
    x, y, inside = _project_catalog(wcs, catalog, width, height)
    kept = _drop_unresolved_companions(catalog, np.flatnonzero(inside))
    if observer is not None and len(kept):
        ra = np.array([catalog[int(i)]["ra_deg"] for i in kept], dtype=float)
        dec = np.array([catalog[int(i)]["dec_deg"] for i in kept], dtype=float)
        above = _altitudes(observer, ra, dec) > 0.0
        kept = kept[above]
    if image is not None and len(kept):
        on_sky = _on_sky(image, x[kept], y[kept])
        kept = kept[on_sky]
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
    constellations = load_constellations()
    above_horizon = _above_horizon(constellations, observer)
    return {
        "stars": stars,
        "constellations": _project_constellations(
            wcs, constellations, width, height, above_horizon
        ),
        "stats": {
            "stars_expected": expected,
            "stars_matched": int(np.count_nonzero(detected)) if expected else 0,
            # Stars on the sky inside the frame. UnderTheHood labels this
            # "Catalog stars in frame".
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
    """True where a source was claimed. One source, one star.

    Pairs within radius are claimed first, closer pair first and the brighter
    star on an exact tie. A still-unmatched star of magnitude _BRIGHT_MAG or
    brighter may then claim an unused source out to _BRIGHT_RADIUS_PX, but
    only when no other catalog star is closer to that source.
    """
    matched = np.zeros(len(star_x), dtype=bool)
    if len(star_x) == 0 or len(sources) == 0:
        return matched
    distance = np.hypot(star_x[:, None] - sources[:, 0], star_y[:, None] - sources[:, 1])
    used_sources = np.zeros(len(sources), dtype=bool)
    star_index, source_index = np.nonzero(distance <= radius)
    if len(star_index):
        # Closer pair first. An equal distance goes to the brighter star.
        order = np.lexsort((star_mag[star_index], distance[star_index, source_index]))
        for pair in order:
            star = int(star_index[pair])
            source = int(source_index[pair])
            if matched[star] or used_sources[source]:
                continue
            matched[star] = True
            used_sources[source] = True
    wide = _BRIGHT_RADIUS_PX
    if wide <= radius:
        return matched
    bright = np.flatnonzero((~matched) & (star_mag <= _BRIGHT_MAG))
    free = np.flatnonzero(~used_sources)
    if len(bright) == 0 or len(free) == 0:
        return matched
    wide_dist = distance[np.ix_(bright, free)]
    nearest_local = np.argmin(wide_dist, axis=1)
    nearest_d = wide_dist[np.arange(len(bright)), nearest_local]
    for k in np.argsort(nearest_d):
        if nearest_d[k] > wide or used_sources[int(free[nearest_local[k]])]:
            continue
        star = int(bright[k])
        source = int(free[nearest_local[k]])
        if int(np.argmin(distance[:, source])) != star:
            continue
        matched[star] = True
        used_sources[source] = True
    return matched


def _observer(lat, lon, taken_at):
    if lat is None and lon is None and taken_at is None:
        return None
    if lat is None or lon is None or taken_at is None:
        raise ValueError("lat, lon, and taken_at must be passed together")
    return (lat, lon, taken_at)


def _altitudes(observer, ra_deg, dec_deg):
    from app.conditions import altitudes_deg

    lat, lon, taken_at = observer
    return altitudes_deg(lat, lon, taken_at, ra_deg, dec_deg)


def _drop_unresolved_companions(catalog, indices):
    """Drop the fainter star of a pair closer than _COMPANION_ARCSEC.

    Only pairs whose declinations already agree within that angle are
    measured, so this stays a short walk instead of a sky-wide search.
    """
    indices = np.asarray(indices, dtype=int)
    count = len(indices)
    if count < 2:
        return indices
    ra = np.array([catalog[int(i)]["ra_deg"] for i in indices], dtype=float)
    dec = np.array([catalog[int(i)]["dec_deg"] for i in indices], dtype=float)
    mag = np.array([catalog[int(i)]["mag"] for i in indices], dtype=float)
    limit_deg = _COMPANION_ARCSEC / 3600.0
    order = np.argsort(dec)
    drop = np.zeros(count, dtype=bool)
    start = 0
    for pos in range(count):
        while dec[order[pos]] - dec[order[start]] > limit_deg:
            start += 1
        for other in range(start, pos):
            a = int(order[other])
            b = int(order[pos])
            if _separation_arcsec(ra[a], dec[a], ra[b], dec[b]) >= _COMPANION_ARCSEC:
                continue
            fainter = b if mag[b] > mag[a] or (mag[b] == mag[a] and b > a) else a
            drop[fainter] = True
    return indices[~drop]


def _separation_arcsec(ra1, dec1, ra2, dec2):
    dra = (ra1 - ra2 + 180.0) % 360.0 - 180.0
    dra_rad = np.radians(dra) * np.cos(np.radians((dec1 + dec2) / 2.0))
    ddec_rad = np.radians(dec1 - dec2)
    return float(np.degrees(np.hypot(dra_rad, ddec_rad)) * 3600.0)


def _on_sky(image, xs, ys):
    """False where the annulus around a star is bright foreground.

    A dark lake is not bright, so this does not replace the horizon cut.
    An unreadable image keeps every star.
    """
    rgb = _rgb(image)
    keep = np.ones(len(xs), dtype=bool)
    if rgb is None or len(xs) == 0:
        return keep
    height, width = rgb.shape[:2]
    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    outer = _ANNULUS_OUTER_PX
    yy, xx = np.ogrid[-outer : outer + 1, -outer : outer + 1]
    ring = (xx * xx + yy * yy >= _ANNULUS_INNER_PX ** 2) & (xx * xx + yy * yy <= outer ** 2)
    for index, (x, y) in enumerate(zip(xs, ys)):
        cx, cy = int(round(float(x))), int(round(float(y)))
        x0, y0 = cx - outer, cy - outer
        x1, y1 = cx + outer + 1, cy + outer + 1
        rx0, ry0 = max(x0, 0), max(y0, 0)
        rx1, ry1 = min(x1, width), min(y1, height)
        if rx0 >= rx1 or ry0 >= ry1:
            continue
        sample = luma[ry0:ry1, rx0:rx1][ring[ry0 - y0 : ry1 - y0, rx0 - x0 : rx1 - x0]]
        if sample.size < 20:
            continue
        if float(np.median(sample)) >= _FOREGROUND_LUMA:
            keep[index] = False
    return keep


def _rgb(image):
    if isinstance(image, np.ndarray):
        array = np.asarray(image)
        if array.ndim == 2:
            array = np.stack((array, array, array), axis=-1)
        if array.ndim != 3 or array.shape[2] < 3:
            return None
        return array[:, :, :3].astype(np.float32, copy=False)
    try:
        from PIL import Image

        with Image.open(image) as opened:
            return np.asarray(opened.convert("RGB"), dtype=np.float32)
    except (OSError, ValueError):
        return None


def _above_horizon(constellations, observer):
    """Map rounded (ra, dec) of every stick-figure vertex to alt > 0.

    None when no observer was given, which leaves the lines unchanged.
    """
    if observer is None:
        return None
    ra, dec = [], []
    for constellation in constellations:
        for start, end in constellation["lines"]:
            ra.extend((start[0], end[0]))
            dec.extend((start[1], end[1]))
    if not ra:
        return {}
    alts = _altitudes(observer, np.asarray(ra, dtype=float), np.asarray(dec, dtype=float))
    above = {}
    for ra_i, dec_i, alt in zip(ra, dec, np.asarray(alts).ravel()):
        above[(round(float(ra_i), 6), round(float(dec_i), 6))] = float(alt) > 0.0
    return above


def _project_constellations(wcs, constellations, width, height, above_horizon=None):
    figures = []
    for constellation in constellations:
        segments = []
        in_frame = []
        seen = set()
        for start, end in constellation["lines"]:
            if above_horizon is not None:
                start_key = (round(float(start[0]), 6), round(float(start[1]), 6))
                end_key = (round(float(end[0]), 6), round(float(end[1]), 6))
                if not above_horizon.get(start_key, False) or not above_horizon.get(end_key, False):
                    continue
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
