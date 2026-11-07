"""Draw catalog stars on a solved photo so a y-flip is obvious. Dev tool only.

The app never imports this. From backend/:

    .venv/bin/python scripts/overlay_check.py \\
        --image photo.jpg --wcs wcs.fits --axy axy.fits --corr corr.fits

Matching and the yellow dots use every extracted source in the .axy file
(1-based FITS pixels, shifted to image pixels by sources_from_axy). corr.fits
is only the solver's matched pairs, so it is optional and is used only to
print median_pair_px. The photo must be the same pixels the WCS was solved on.

Writes overlay_check.png in the current directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image, ImageDraw, ImageFont

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.matching import _load_wcs, _sky_to_image, match_stars
from app.solver import fits_xy_to_image, sources_from_axy


def main():
    args = _parse_args()
    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    _warn_if_size_differs(args.wcs, width, height)

    with fits.open(args.axy) as axy:
        sources = sources_from_axy(axy)
    result = match_stars(args.wcs, width, height, sources)

    _draw(image, result, [s["x"] for s in sources], [s["y"] for s in sources])
    out = Path("overlay_check.png")
    image.save(out)

    stats = result["stats"]
    print(f"stars_expected: {stats['stars_expected']}")
    print(f"stars_matched: {stats['stars_matched']}")
    if args.corr is not None:
        field_x, field_y, index_ra, index_dec = _read_corr(args.corr)
        image_x, image_y = fits_xy_to_image(field_x, field_y)
        median_px = _median_pair_distance(args.wcs, index_ra, index_dec, image_x, image_y)
        print(f"median_pair_px: {median_px:.2f}")
    print(f"wrote {out.resolve()}")


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="the photo that was solved")
    parser.add_argument("--wcs", required=True, type=Path, help="wcs.fits from the solved job")
    parser.add_argument("--axy", required=True, type=Path, help="full .axy extraction; sources for matching")
    parser.add_argument("--corr", type=Path, help="optional corr.fits, used only for median_pair_px")
    return parser.parse_args()


def _warn_if_size_differs(wcs_path, width, height):
    header = fits.getheader(wcs_path)
    solved_w = header.get("IMAGEW")
    solved_h = header.get("IMAGEH")
    if solved_w is None or solved_h is None:
        return
    if int(solved_w) != width or int(solved_h) != height:
        print(
            f"warning: photo is {width}x{height} but the WCS says "
            f"{int(solved_w)}x{int(solved_h)}. The overlay only means something "
            "when both are the same pixels.",
            file=sys.stderr,
        )


def _read_corr(path):
    with fits.open(path) as hdul:
        table = hdul[1].data
        columns = {name.lower(): name for name in table.columns.names}
        needed = ("field_x", "field_y", "index_ra", "index_dec")
        missing = [name for name in needed if name not in columns]
        if missing:
            raise SystemExit(f"{path} is missing columns: {', '.join(missing)}")
        return tuple(np.asarray(table[columns[name]], dtype=float) for name in needed)


def _median_pair_distance(wcs_path, index_ra, index_dec, image_x, image_y):
    """How far each corr index star projects from that row's field pixel."""
    if len(index_ra) == 0:
        return float("nan")
    projected_x, projected_y = _sky_to_image(_load_wcs(wcs_path), index_ra, index_dec)
    distance = np.hypot(projected_x - image_x, projected_y - image_y)
    return float(np.median(distance))


def _draw(image, result, source_x, source_y):
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    unit = max(image.size) / 1000.0
    arm = max(3.0, 5.0 * unit)
    ring = max(5.0, 9.0 * unit)
    dot = max(1.5, 2.5 * unit)
    line_width = max(1, int(round(unit)))

    for figure in result["constellations"]:
        for x1, y1, x2, y2 in figure["lines"]:
            draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255), width=line_width)

    for star in result["stars"]:
        if star["detected"]:
            continue
        x, y = star["x"], star["y"]
        draw.line([(x - arm, y - arm), (x + arm, y + arm)], fill=(230, 40, 40), width=line_width)
        draw.line([(x - arm, y + arm), (x + arm, y - arm)], fill=(230, 40, 40), width=line_width)

    for x, y in zip(source_x, source_y):
        draw.ellipse([x - dot, y - dot, x + dot, y + dot], fill=(255, 220, 0))

    for star in result["stars"]:
        if not star["detected"]:
            continue
        x, y = star["x"], star["y"]
        draw.ellipse([x - ring, y - ring, x + ring, y + ring], outline=(40, 220, 70), width=line_width + 1)
        if star["mag"] < 2 and star["name"]:
            draw.text((x + ring + 2, y - arm), star["name"], fill=(255, 255, 255), font=font)


if __name__ == "__main__":
    main()
