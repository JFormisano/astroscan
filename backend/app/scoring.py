"""Limiting magnitude, 1–9 score, percent lost, and confidence. Owner: Person B.

The 1–9 number follows the published naked-eye limits in data/calibration.json.
It is an estimate until those bounds are replaced with our own photos.
pct_lost is 0–100, the same scale as demo_cache and ScoreCard.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

_CALIBRATION_PATH = Path(__file__).resolve().parent.parent / "data" / "calibration.json"
_BIN_WIDTH = 0.5
_NAKED_EYE_MAG = 6.0
_CONFIDENCE = ("high", "medium", "low")
# The catalog ends at magnitude 7, so a measured limit of 7.0 is only a floor.
# Classes darker than the one that matches 7.0 (score 3) cannot be told apart.
# A code, not a sentence. The results page accepts either form.
_CATALOG_LIMIT_REASON = "catalog_limit"


def score_sky(match_result, conditions, exif):
    """Score one matched photo.

    match_result is the dict from match_stars (stars with mag and detected,
    stats.stars_matched). conditions is the dict from evaluate_conditions.
    exif may leave exposure_s, iso, or f_number as None.
    """
    table = _load_calibration()
    stars = list(match_result.get("stars") or [])
    bins = _bins(stars)
    limiting_mag, is_lower_bound = _limiting_magnitude(bins, int(table["min_bin_stars"]))
    pct_lost = _percent_lost(stars)
    reasons = _confidence_reasons(match_result, conditions, exif, table, is_lower_bound)
    return {
        "value": _score_value(limiting_mag, table["classes"]),
        "limiting_mag": limiting_mag,
        "limiting_mag_is_lower_bound": is_lower_bound,
        "pct_lost": pct_lost,
        "confidence": _CONFIDENCE[min(len(reasons), len(_CONFIDENCE) - 1)],
        "confidence_reasons": reasons,
        "bins": bins,
    }


@lru_cache(maxsize=1)
def _load_calibration():
    with _CALIBRATION_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _bins(stars):
    """Every 0.5-mag bin that contains a star, bright bins first."""
    grouped = {}
    for star in stars:
        index = math.floor(float(star["mag"]) / _BIN_WIDTH)
        expected, detected = grouped.get(index, (0, 0))
        expected += 1
        if star.get("detected"):
            detected += 1
        grouped[index] = (expected, detected)
    bins = []
    for index in sorted(grouped):
        expected, detected = grouped[index]
        mag_min = round(index * _BIN_WIDTH, 1)
        bins.append(
            {
                "mag_min": mag_min,
                "mag_max": round(mag_min + _BIN_WIDTH, 1),
                "expected": expected,
                "detected": detected,
            }
        )
    return bins


def _limiting_magnitude(bins, min_stars):
    """Where detection falls below 50%, and whether that magnitude is only a floor.

    Bins with fewer than min_stars stars are ignored. Exactly 50% still counts
    as detected. The limit is the bright edge of the first counted bin under
    50%. If every counted bin stays at or above 50%, the sky is darker than
    the catalog can measure: the limit is the faint edge of the faintest
    counted bin (about 7.0) and the second value is True. None only when no
    bin has enough stars to judge.
    """
    faintest = None
    for item in bins:
        if item["expected"] < min_stars:
            continue
        faintest = item
        if item["detected"] / item["expected"] < 0.5:
            return item["mag_min"], False
    if faintest is None:
        return None, False
    return faintest["mag_max"], True


def _percent_lost(stars):
    """Percent of catalog stars brighter than magnitude 6 that were not detected."""
    bright = [star for star in stars if float(star["mag"]) < _NAKED_EYE_MAG]
    if not bright:
        return None
    detected = sum(1 for star in bright if star.get("detected"))
    return round(100.0 * (1.0 - detected / len(bright)), 1)


def _score_value(limiting_mag, classes):
    if limiting_mag is None:
        return None
    ordered = sorted(classes, key=lambda item: item["value"])
    for item in ordered:
        floor = item["min_limiting_mag"]
        if floor is not None and limiting_mag >= floor:
            return int(item["value"])
    return int(ordered[-1]["value"])


def _confidence_reasons(match_result, conditions, exif, table, is_lower_bound):
    reasons = []
    flags = (conditions or {}).get("flags") or {}
    for name in ("twilight", "moon_up", "low_altitude"):
        if flags.get(name):
            reasons.append(name)

    stats = (match_result or {}).get("stats") or {}
    if "stars_matched" in stats:
        matched = int(stats["stars_matched"])
    else:
        matched = sum(1 for star in (match_result.get("stars") or []) if star.get("detected"))
    if matched < int(table["few_matched_stars"]):
        reasons.append("few_matched_stars")

    exif = exif or {}
    exposure = exif.get("exposure_s")
    iso = exif.get("iso")
    if exposure is None or iso is None or exif.get("f_number") is None:
        reasons.append("missing_exif")
    window = table["exposure"]
    low_s, high_s = window["exposure_s"]
    low_iso, high_iso = window["iso"]
    if exposure is not None and not (low_s <= float(exposure) <= high_s):
        reasons.append("exposure_out_of_range")
    if iso is not None and not (low_iso <= float(iso) <= high_iso):
        reasons.append("iso_out_of_range")
    if is_lower_bound:
        reasons.append(_CATALOG_LIMIT_REASON)
    return reasons
