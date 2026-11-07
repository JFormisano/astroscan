"""Sun, Moon, and planet geometry for one photo.

Owner: Person B. This module only returns numbers. Warning banners belong to Person C.
Altitudes are geometric (no atmospheric refraction), so the twilight cut at -18°
matches the astronomical definition. Planet RA/Dec is J2000.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import astronomy

# Mercury through Saturn, in outward order. Uranus and Neptune are too faint
# for a phone photo of the sky, so they are left out.
_PLANETS = (
    ("Mercury", astronomy.Body.Mercury),
    ("Venus", astronomy.Body.Venus),
    ("Mars", astronomy.Body.Mars),
    ("Jupiter", astronomy.Body.Jupiter),
    ("Saturn", astronomy.Body.Saturn),
)

_TWILIGHT_ALT_DEG = -18.0
_HORIZON_ALT_DEG = 0.0
_LOW_ALTITUDE_DEG = 30.0
_HOURS_TO_DEG = 15.0


def evaluate_conditions(lat, lon, taken_at, ra_deg=None, dec_deg=None):
    """Return Sun, Moon, field-center, and planet geometry for one instant.

    lat, lon, ra_deg, and dec_deg are degrees. taken_at is an ISO 8601
    timestamp that must include a timezone; a naive string raises ValueError.
    ra_deg and dec_deg are the field center in J2000 and must be passed
    together. field_center_alt_deg is None when they are omitted.
    """
    lat_deg = _require_degrees("lat", lat, -90.0, 90.0)
    lon_deg = _require_degrees("lon", lon, -180.0, 180.0)
    field_center = _require_field_center(ra_deg, dec_deg)
    time = _parse_taken_at(taken_at)
    observer = astronomy.Observer(lat_deg, lon_deg, 0.0)

    sun_alt_deg = _body_horizontal(astronomy.Body.Sun, time, observer).altitude
    moon_alt_deg = _body_horizontal(astronomy.Body.Moon, time, observer).altitude
    moon_illumination_pct = (
        astronomy.Illumination(astronomy.Body.Moon, time).phase_fraction * 100.0
    )

    if field_center is None:
        field_center_alt_deg = None
        low_altitude = False
    else:
        field_ra_deg, field_dec_deg = field_center
        field_center_alt_deg = _j2000_altitude_deg(
            time, observer, field_ra_deg, field_dec_deg
        )
        low_altitude = field_center_alt_deg < _LOW_ALTITUDE_DEG

    return {
        "sun_alt_deg": float(sun_alt_deg),
        "moon_alt_deg": float(moon_alt_deg),
        "moon_illumination_pct": float(moon_illumination_pct),
        "field_center_alt_deg": (
            None if field_center_alt_deg is None else float(field_center_alt_deg)
        ),
        "flags": {
            "twilight": bool(sun_alt_deg > _TWILIGHT_ALT_DEG),
            "moon_up": bool(moon_alt_deg > _HORIZON_ALT_DEG),
            "low_altitude": bool(low_altitude),
        },
        "planets": [_planet(name, body, time, observer) for name, body in _PLANETS],
    }


def _require_degrees(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number of degrees")
    degrees = float(value)
    if not math.isfinite(degrees) or degrees < low or degrees > high:
        raise ValueError(f"{name} must be between {low:g} and {high:g} degrees")
    return degrees


def _require_field_center(ra_deg, dec_deg):
    if ra_deg is None and dec_deg is None:
        return None
    if ra_deg is None or dec_deg is None:
        raise ValueError("ra_deg and dec_deg must be passed together")
    if isinstance(ra_deg, bool) or not isinstance(ra_deg, (int, float)):
        raise ValueError("ra_deg must be a number of degrees")
    if isinstance(dec_deg, bool) or not isinstance(dec_deg, (int, float)):
        raise ValueError("dec_deg must be a number of degrees")
    ra = float(ra_deg)
    dec = float(dec_deg)
    if not math.isfinite(ra) or not math.isfinite(dec):
        raise ValueError("ra_deg and dec_deg must be finite")
    if dec < -90.0 or dec > 90.0:
        raise ValueError("dec_deg must be between -90 and 90 degrees")
    return ra, dec


def _parse_taken_at(taken_at):
    """Parse an ISO 8601 timestamp and return an astronomy-engine Time in UTC.

    A string with no offset is rejected. Callers convert local EXIF time to
    UTC before they get here; guessing an offset would silently move the Sun.
    """
    if not isinstance(taken_at, str):
        raise ValueError("taken_at must be an ISO 8601 string with a timezone")
    text = taken_at.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"taken_at is not a valid ISO 8601 timestamp: {taken_at}") from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ValueError(
            "taken_at must include a timezone, for example 2026-11-15T17:00:00Z"
        )
    utc = parsed.astimezone(timezone.utc)
    millis = utc.microsecond // 1000
    stamp = utc.strftime("%Y-%m-%dT%H:%M:%S") + f".{millis:03d}Z"
    return astronomy.Time.Parse(stamp)


def _body_horizontal(body, time, observer):
    """Altitude and azimuth of a solar-system body. RA argument is hours."""
    of_date = astronomy.Equator(
        body, time, observer, ofdate=True, aberration=True
    )
    return astronomy.Horizon(
        time,
        observer,
        of_date.ra,
        of_date.dec,
        astronomy.Refraction.Airless,
    )


def _j2000_altitude_deg(time, observer, ra_deg, dec_deg):
    """Geometric altitude of a fixed J2000 direction.

    The solver reports the field center in J2000 degrees. Horizon() needs
    equator-of-date coordinates, and it takes right ascension in sidereal hours.
    """
    eqj = astronomy.VectorFromSphere(
        astronomy.Spherical(dec_deg, ra_deg % 360.0, 1.0),
        time,
    )
    of_date_vec = astronomy.RotateVector(astronomy.Rotation_EQJ_EQD(time), eqj)
    of_date = astronomy.EquatorFromVector(of_date_vec)
    horizontal = astronomy.Horizon(
        time,
        observer,
        of_date.ra,
        of_date.dec,
        astronomy.Refraction.Airless,
    )
    return horizontal.altitude


def _planet(name, body, time, observer):
    j2000 = astronomy.Equator(
        body, time, observer, ofdate=False, aberration=True
    )
    horizontal = _body_horizontal(body, time, observer)
    # Equator.ra is sidereal hours. Degrees are the API boundary.
    ra_deg = j2000.ra * _HOURS_TO_DEG
    alt_deg = float(horizontal.altitude)
    return {
        "name": name,
        "ra_deg": float(ra_deg),
        "dec_deg": float(j2000.dec),
        "alt_deg": alt_deg,
        "az_deg": float(horizontal.azimuth),
        "magnitude": float(astronomy.Illumination(body, time).mag),
        "above_horizon": bool(alt_deg > _HORIZON_ALT_DEG),
    }
