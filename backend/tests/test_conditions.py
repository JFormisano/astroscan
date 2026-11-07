"""Known-answer tests for Sun, Moon, and planet geometry.

Buffalo / UB: 43.0 N, 78.79 W. Daylight saving time ended on 2026-11-01,
so a November local time is EST (UTC-5). Clock noon is 17:00 UTC and
local midnight is 05:00 UTC.
"""

import json

import astronomy
import pytest

from app.conditions import evaluate_conditions

BUFFALO_LAT = 43.0
BUFFALO_LON = -78.79
# 2026-11-15 12:00 EST.
NOON_UTC = "2026-11-15T17:00:00Z"
# 2026-11-16 00:00 EST.
MIDNIGHT_UTC = "2026-11-16T05:00:00Z"

# Polaris J2000 mean place: 02h 31m 49.09s, +89° 15' 50.8".
POLARIS_RA_DEG = (2 + 31 / 60 + 49.09 / 3600) * 15
POLARIS_DEC_DEG = 89 + 15 / 60 + 50.8 / 3600


def test_sun_above_horizon_at_local_noon():
    result = evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, NOON_UTC)
    assert result["sun_alt_deg"] > 0
    assert result["flags"]["twilight"] is True


def test_sun_below_astronomical_twilight_at_local_midnight():
    result = evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, MIDNIGHT_UTC)
    assert result["sun_alt_deg"] < -18
    assert result["flags"]["twilight"] is False


def test_polaris_altitude_matches_observer_latitude():
    # Polaris sits 0.74° from the pole, so its altitude stays within about
    # a degree of the observer's latitude all night.
    result = evaluate_conditions(
        BUFFALO_LAT,
        BUFFALO_LON,
        MIDNIGHT_UTC,
        ra_deg=POLARIS_RA_DEG,
        dec_deg=POLARIS_DEC_DEG,
    )
    assert result["field_center_alt_deg"] == pytest.approx(BUFFALO_LAT, abs=1.0)


def test_low_altitude_false_near_zenith():
    ra_deg, dec_deg = _j2000_of_horizontal(89.0, 0.0, NOON_UTC)
    result = evaluate_conditions(
        BUFFALO_LAT, BUFFALO_LON, NOON_UTC, ra_deg=ra_deg, dec_deg=dec_deg
    )
    assert result["field_center_alt_deg"] == pytest.approx(89.0, abs=0.05)
    assert result["flags"]["low_altitude"] is False


def test_low_altitude_true_near_horizon():
    ra_deg, dec_deg = _j2000_of_horizontal(5.0, 180.0, NOON_UTC)
    result = evaluate_conditions(
        BUFFALO_LAT, BUFFALO_LON, NOON_UTC, ra_deg=ra_deg, dec_deg=dec_deg
    )
    assert result["field_center_alt_deg"] == pytest.approx(5.0, abs=0.05)
    assert result["flags"]["low_altitude"] is True


def test_omitted_field_center_is_null():
    result = evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, MIDNIGHT_UTC)
    assert "field_center_alt_deg" in result
    assert result["field_center_alt_deg"] is None
    assert result["flags"]["low_altitude"] is False


def test_moon_illumination_is_a_percentage():
    result = evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, NOON_UTC)
    assert 0.0 <= result["moon_illumination_pct"] <= 100.0


def test_naive_taken_at_raises():
    with pytest.raises(ValueError):
        evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, "2026-11-15T17:00:00")


def test_result_is_json_serializable():
    result = evaluate_conditions(
        BUFFALO_LAT,
        BUFFALO_LON,
        NOON_UTC,
        ra_deg=POLARIS_RA_DEG,
        dec_deg=POLARIS_DEC_DEG,
    )
    json.dumps(result)
    assert set(result) == {
        "sun_alt_deg",
        "moon_alt_deg",
        "moon_illumination_pct",
        "field_center_alt_deg",
        "flags",
        "planets",
    }
    assert set(result["flags"]) == {"twilight", "moon_up", "low_altitude"}
    assert [planet["name"] for planet in result["planets"]] == [
        "Mercury",
        "Venus",
        "Mars",
        "Jupiter",
        "Saturn",
    ]
    for planet in result["planets"]:
        assert planet["above_horizon"] is (planet["alt_deg"] > 0)


def test_offset_timestamp_matches_the_same_utc_instant():
    # 12:00 EST is 17:00 UTC. The offset is written out; nothing is inferred.
    from_z = evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, NOON_UTC)
    from_offset = evaluate_conditions(
        BUFFALO_LAT, BUFFALO_LON, "2026-11-15T12:00:00-05:00"
    )
    assert from_offset["sun_alt_deg"] == pytest.approx(from_z["sun_alt_deg"], abs=1e-4)


def test_latitude_and_longitude_bounds():
    with pytest.raises(ValueError):
        evaluate_conditions(90.1, BUFFALO_LON, NOON_UTC)
    with pytest.raises(ValueError):
        evaluate_conditions(BUFFALO_LAT, 180.1, NOON_UTC)


def test_field_center_coordinates_must_be_passed_together():
    with pytest.raises(ValueError):
        evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, NOON_UTC, ra_deg=10.0)
    with pytest.raises(ValueError):
        evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, NOON_UTC, dec_deg=10.0)


@pytest.mark.skip(
    reason="TODO: paste Stellarium J2000 RA/Dec for Jupiter, then remove this skip"
)
def test_jupiter_position_matches_stellarium():
    """TODO(Person B): replace the two placeholder numbers, then unskip.

    Stellarium setup for this check:
      date and time: 2026-11-15 17:00:00 UTC
      location: latitude 43.0, longitude -78.79
      equatorial coordinates, epoch J2000
      atmosphere off (these altitudes are geometric)
    Read Jupiter's right ascension and declination in degrees.
    """
    expected_ra_deg = 0.0  # TODO
    expected_dec_deg = 0.0  # TODO
    result = evaluate_conditions(BUFFALO_LAT, BUFFALO_LON, NOON_UTC)
    jupiter = next(planet for planet in result["planets"] if planet["name"] == "Jupiter")
    assert jupiter["ra_deg"] == pytest.approx(expected_ra_deg, abs=0.1)
    assert jupiter["dec_deg"] == pytest.approx(expected_dec_deg, abs=0.1)


def _j2000_of_horizontal(alt_deg, az_deg, taken_at):
    """Invert a geometric altitude/azimuth to J2000 degrees, for fixture setup."""
    time = astronomy.Time.Parse(taken_at.replace("Z", ".000Z"))
    observer = astronomy.Observer(BUFFALO_LAT, BUFFALO_LON, 0.0)
    horizontal = astronomy.VectorFromHorizon(
        astronomy.Spherical(alt_deg, az_deg, 1.0),
        time,
        astronomy.Refraction.Airless,
    )
    eqj = astronomy.RotateVector(astronomy.Rotation_HOR_EQJ(time, observer), horizontal)
    direction = astronomy.SphereFromVector(eqj)
    return direction.lon, direction.lat
