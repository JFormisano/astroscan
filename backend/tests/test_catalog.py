"""Checks on the generated star catalog and constellation stick figures."""

import pytest

from app.matching import load_constellations, load_stars

# J2000 places, loose enough to absorb catalog rounding.
# Sirius in HYG v4.4 is magnitude -1.44; -1.46 is the usual rounded value.
SIRIUS = {"ra_deg": 101.29, "dec_deg": -16.72, "mag": -1.46, "hip": 32349}
POLARIS = {"ra_deg": 37.95, "dec_deg": 89.26, "mag": 1.97, "hip": 11767}
BETELGEUSE = {"ra_deg": 88.79, "dec_deg": 7.41, "mag": 0.45, "hip": 27989}


def test_named_stars_have_sensible_positions():
    stars = {star["proper"]: star for star in load_stars() if star["proper"]}
    for name, expected in (
        ("Sirius", SIRIUS),
        ("Polaris", POLARIS),
        ("Betelgeuse", BETELGEUSE),
    ):
        star = stars[name]
        assert star["hip"] == expected["hip"]
        assert star["ra_deg"] == pytest.approx(expected["ra_deg"], abs=0.05)
        assert star["dec_deg"] == pytest.approx(expected["dec_deg"], abs=0.05)
        assert star["mag"] == pytest.approx(expected["mag"], abs=0.05)


def test_no_star_is_brighter_than_minus_two():
    # The Sun is magnitude about -26.7. Nothing else in HYG is below -2.
    for star in load_stars():
        assert star["mag"] >= -2
        assert star["id"] != 0


def test_blank_names_are_null():
    for star in load_stars():
        assert star["proper"] is None or star["proper"] != ""
        assert star["bayer_flamsteed"] is None or star["bayer_flamsteed"] != ""
        assert "hip" in star


def test_exactly_88_constellations():
    constellations = load_constellations()
    abbreviations = [item["abbreviation"] for item in constellations]
    assert len(constellations) == 88
    assert len(set(abbreviations)) == 88


def test_vela_has_iau_name_and_english_name():
    vela = next(item for item in load_constellations() if item["abbreviation"] == "Vel")
    assert vela["name"] == "Vela"
    assert vela["common_name"] == "Sails"


def test_line_endpoints_are_on_the_sky():
    for constellation in load_constellations():
        assert constellation["lines"], constellation["abbreviation"]
        for segment in constellation["lines"]:
            assert len(segment) == 2
            for ra_deg, dec_deg in segment:
                assert 0 <= ra_deg <= 360
                assert -90 <= dec_deg <= 90


def test_loaders_read_each_file_once():
    assert load_stars() is load_stars()
    assert load_constellations() is load_constellations()
