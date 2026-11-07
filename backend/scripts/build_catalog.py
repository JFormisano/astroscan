"""Build the star catalog and constellation stick figures used by matching.

Reads the HYG v4.4 catalog and Stellarium's modern sky culture, both
downloaded by hand (see backend/data/README.md). The standard library is
enough: no extra packages.

Run from anywhere:

    python backend/scripts/build_catalog.py \\
        --hyg backend/data/raw/hyg_v44.csv.gz \\
        --stellarium backend/data/raw/stellarium_modern_index.json
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

# HYG's first row is the Sun: id 0, magnitude about -26.7, RA/Dec 0,0.
# Leaving it in would project a fake star on top of every photo.
_SUN_ID = 0

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_STARS_PATH = _DATA_DIR / "stars.json"
_LINES_PATH = _DATA_DIR / "constellation_lines.json"


def main():
    args = _parse_args()
    hip_positions, stars = _read_hyg(args.hyg)
    constellations = _read_constellations(args.stellarium, hip_positions)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(_STARS_PATH, stars)
    _write_json(_LINES_PATH, constellations)
    segments = sum(len(item["lines"]) for item in constellations)
    print(f"stars: {len(stars)}")
    print(f"constellations: {len(constellations)}")
    print(f"segments: {segments}")
    print(f"{_STARS_PATH}: {_human_size(_STARS_PATH.stat().st_size)}")
    print(f"{_LINES_PATH}: {_human_size(_LINES_PATH.stat().st_size)}")


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hyg", required=True, type=Path, help="HYG v4.4 csv or csv.gz")
    parser.add_argument(
        "--stellarium",
        required=True,
        type=Path,
        help="Stellarium modern sky culture index.json",
    )
    return parser.parse_args()


def _read_hyg(path):
    """Return (hip → (ra_deg, dec_deg), stars with magnitude <= 7)."""
    _reject_lfs_pointer(path)
    hip_positions = {}
    stars = []
    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        required = {"id", "hip", "proper", "bf", "con", "ra", "dec", "mag"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path} is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            star_id = int(row["id"])
            ra_deg = _ra_hours_to_deg(row["ra"])
            dec_deg = _dec_deg(row["dec"])
            hip = _optional_int(row["hip"])
            if hip is not None:
                hip_positions[hip] = (ra_deg, dec_deg)
            if star_id == _SUN_ID:
                continue
            magnitude = _optional_float(row["mag"])
            if magnitude is None or magnitude > 7.0:
                continue
            stars.append(
                {
                    "id": star_id,
                    "hip": hip,
                    "proper": _blank_to_none(row["proper"]),
                    "bayer_flamsteed": _blank_to_none(row["bf"]),
                    "constellation": _blank_to_none(row["con"]),
                    "ra_deg": ra_deg,
                    "dec_deg": dec_deg,
                    "mag": magnitude,
                }
            )
    if not stars:
        raise SystemExit(f"no stars brighter than magnitude 7 in {path}")
    return hip_positions, stars


def _read_constellations(path, hip_positions):
    """88 IAU stick figures. Asterisms and artwork in the same file are ignored."""
    document = json.loads(path.read_text(encoding="utf-8"))
    figures = document.get("constellations")
    if not isinstance(figures, list):
        raise SystemExit(f"{path} has no constellations array")
    constellations = []
    for figure in figures:
        abbreviation = _abbreviation(figure["id"])
        names = figure.get("common_name") or {}
        iau_name = _blank_to_none(names.get("native"))
        if iau_name is None:
            raise SystemExit(f"{abbreviation} has no IAU name in {path}")
        segments = []
        for polyline in figure.get("lines") or []:
            points = [_vertex(abbreviation, hip, hip_positions) for hip in polyline]
            segments.extend(
                [points[index], points[index + 1]] for index in range(len(points) - 1)
            )
        if not segments:
            raise SystemExit(f"{abbreviation} has no line segments")
        constellations.append(
            {
                "abbreviation": abbreviation,
                "name": iau_name,
                "common_name": _blank_to_none(names.get("english")),
                "lines": segments,
            }
        )
    if len(constellations) != 88:
        raise SystemExit(f"expected 88 constellations, found {len(constellations)}")
    return constellations


def _vertex(abbreviation, hip, hip_positions):
    if isinstance(hip, str) and hip.isdigit():
        hip = int(hip)
    if not isinstance(hip, int):
        raise SystemExit(
            f"{abbreviation} has a non-Hipparcos vertex {hip!r}; "
            "only the 88 IAU figures are supported"
        )
    try:
        ra_deg, dec_deg = hip_positions[hip]
    except KeyError:
        raise SystemExit(f"{abbreviation} vertex HIP {hip} is not in the HYG catalog") from None
    return [ra_deg, dec_deg]


def _abbreviation(culture_id):
    # Ids look like "CON modern Ori".
    abbreviation = str(culture_id).split()[-1]
    if len(abbreviation) != 3 or not abbreviation.isalpha():
        raise SystemExit(f"unexpected constellation id {culture_id!r}")
    return abbreviation


def _ra_hours_to_deg(hours_text):
    # HYG right ascension is hours, not degrees. 24 h wraps to 0°.
    degrees = (float(hours_text) * 15.0) % 360.0
    return float(f"{degrees:.6f}")


def _dec_deg(dec_text):
    degrees = float(dec_text)
    if degrees < -90.0 or degrees > 90.0:
        raise SystemExit(f"declination {dec_text} is outside -90..90")
    return float(f"{degrees:.6f}")


def _optional_int(value):
    text = _blank_to_none(value)
    if text is None:
        return None
    return int(float(text))


def _optional_float(value):
    text = _blank_to_none(value)
    if text is None:
        return None
    return float(f"{float(text):.2f}")


def _blank_to_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _open_text(path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", newline="")
    return path.open(newline="")


def _reject_lfs_pointer(path):
    with path.open("rb") as handle:
        head = handle.read(40)
    if head.startswith(b"version https://git-lfs.github.com"):
        raise SystemExit(
            f"{path} is a Git LFS pointer, not the catalog. "
            "Download the LFS object named in data/README.md."
        )


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _human_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
