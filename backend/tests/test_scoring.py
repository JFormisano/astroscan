"""Sky score from synthetic match results. No network."""

import json

from app.scoring import score_sky

GOOD_EXIF = {"exposure_s": 2.0, "iso": 800, "f_number": 1.8}
CLEAR = {"flags": {"twilight": False, "moon_up": False, "low_altitude": False}}


def _stars(detected_before, faint=7.0):
    """Four stars in each 0.5-mag bin. Stars fainter than detected_before are ghosts."""
    stars = []
    edge = 0.0
    while edge < faint:
        for step in range(4):
            mag = edge + 0.1 + step * 0.05
            stars.append({"mag": mag, "detected": mag < detected_before})
        edge = round(edge + 0.5, 1)
    return stars


def _score(stars, matched=20, flags=None, exif=None):
    conditions = {"flags": CLEAR["flags"] if flags is None else flags}
    return score_sky(
        {"stars": stars, "stats": {"stars_matched": matched}},
        conditions,
        GOOD_EXIF if exif is None else exif,
    )


def test_dark_list_scores_lower_than_city_list():
    dark = _score(_stars(6.5))
    city = _score(_stars(4.0))
    assert dark["value"] < city["value"]
    assert dark["limiting_mag"] > city["limiting_mag"]
    assert dark["pct_lost"] < city["pct_lost"]
    assert city["pct_lost"] > 1


def test_zero_stars_in_frame_has_no_score():
    result = _score([], matched=0)
    assert result["value"] is None
    assert result["limiting_mag"] is None
    assert result["limiting_mag_is_lower_bound"] is False
    assert result["pct_lost"] is None
    assert "few_matched_stars" in result["confidence_reasons"]
    assert "sky darker than the catalog can measure" not in result["confidence_reasons"]


def test_all_detected_stars_are_a_lower_bound():
    # Every well-filled bin stays above 50%, so the limit is the faint edge of
    # the catalog (7.0), not an unknown score.
    result = _score(_stars(99))
    assert result["limiting_mag_is_lower_bound"] is True
    assert result["limiting_mag"] == 7.0
    assert result["value"] is not None
    assert result["pct_lost"] == 0
    assert "sky darker than the catalog can measure" in result["confidence_reasons"]


def test_twilight_flag_lowers_confidence():
    clear = _score(_stars(6.5))
    twilight = _score(_stars(6.5), flags={"twilight": True, "moon_up": False, "low_altitude": False})
    assert clear["confidence"] == "high"
    assert twilight["confidence"] == "medium"
    assert twilight["confidence_reasons"] == ["twilight"]


def test_sparse_bin_does_not_set_the_limiting_magnitude():
    # One undetected star in the brightest bin must not pull the limit to 0.
    stars = [{"mag": 0.2, "detected": False}]
    edge = 2.0
    while edge < 4.5:
        for step in range(4):
            stars.append({"mag": edge + 0.1 + step * 0.05, "detected": edge < 4.0})
        edge = round(edge + 0.5, 1)
    result = _score(stars)
    assert result["limiting_mag"] == 4.0
    assert result["value"] == 9


def test_score_is_json_serializable():
    result = _score(_stars(6.5))
    assert json.loads(json.dumps(result)) == result
