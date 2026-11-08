"""Star matching against a synthetic WCS. No network.

The header matches the TAN headers solve-field writes (see make_wcs_header in
test_solver.py): CRPIX is 1-based FITS, CD is degrees per pixel, and image
pixels are the origin=0 coordinates docs/solver-output.md describes.
"""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from app import matching
from app.solver import sources_from_axy

FIXTURES = Path(__file__).parent / "fixtures"
WCS_FIXTURE = FIXTURES / "wcs.fits"
CORR_FIXTURE = FIXTURES / "corr.fits"

# Sirius, from the catalog. A field centred here does not contain Polaris.
SIRIUS_RA = 101.287215
SIRIUS_DEC = -16.716116
SIRIUS_HIP = 32349
POLARIS_HIP = 11767
WIDTH, HEIGHT = 500, 500


def make_tan_header(ra, dec, scale_deg_per_px=0.05, width=WIDTH, height=HEIGHT):
    """Same layout as the solver tests' make_wcs_header."""
    header = fits.Header()
    header["WCSAXES"] = 2
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = (width + 1) / 2
    header["CRPIX2"] = (height + 1) / 2
    header["CRVAL1"] = ra
    header["CRVAL2"] = dec
    header["CD1_1"] = -scale_deg_per_px
    header["CD1_2"] = 0.0
    header["CD2_1"] = 0.0
    header["CD2_2"] = scale_deg_per_px
    header["IMAGEW"] = width
    header["IMAGEH"] = height
    return header


def test_sources_at_catalog_pixels_are_all_detected():
    header = make_tan_header(SIRIUS_RA, SIRIUS_DEC)
    placed = matching.match_stars(header, WIDTH, HEIGHT, [])
    sirius = next(star for star in placed["stars"] if star["hip"] == SIRIUS_HIP)
    others = [star for star in placed["stars"] if star["hip"] != SIRIUS_HIP][:2]
    sample = [sirius, *others]
    assert len(sample) == 3
    sources = [{"x": star["x"], "y": star["y"]} for star in sample]
    result = matching.match_stars(dict(header), WIDTH, HEIGHT, sources)
    by_hip = {star["hip"]: star for star in result["stars"]}
    for star in sample:
        assert by_hip[star["hip"]]["detected"] is True
    assert result["stats"]["stars_matched"] >= 3
    assert result["stats"]["catalog_in_frame"] == result["stats"]["stars_expected"]
    assert result["stats"]["stars_expected"] == len(result["stars"])


def test_removing_a_source_turns_that_star_into_a_ghost():
    header = make_tan_header(SIRIUS_RA, SIRIUS_DEC)
    placed = matching.match_stars(header, WIDTH, HEIGHT, [])
    sirius = next(star for star in placed["stars"] if star["hip"] == SIRIUS_HIP)
    other = next(star for star in placed["stars"] if star["hip"] != SIRIUS_HIP)
    sources = [{"x": sirius["x"], "y": sirius["y"]}, (other["x"], other["y"])]
    both = matching.match_stars(header, WIDTH, HEIGHT, sources)
    both_by_hip = {star["hip"]: star for star in both["stars"]}
    assert both_by_hip[SIRIUS_HIP]["detected"] is True
    assert both_by_hip[other["hip"]]["detected"] is True

    only_other = matching.match_stars(header, WIDTH, HEIGHT, [(other["x"], other["y"])])
    ghosts = {star["hip"]: star for star in only_other["stars"]}
    assert ghosts[SIRIUS_HIP]["detected"] is False
    assert ghosts[other["hip"]]["detected"] is True
    assert ghosts[SIRIUS_HIP]["name"] == "Sirius"


def test_pixel_round_trip_is_within_a_hundredth_of_a_pixel():
    wcs = matching._load_wcs(make_tan_header(SIRIUS_RA, SIRIUS_DEC))
    ra, dec = matching._image_to_sky(wcs, 10.0, 20.0)
    x, y = matching._sky_to_image(wcs, float(ra), float(dec))
    assert float(x) == pytest.approx(10.0, abs=0.01)
    assert float(y) == pytest.approx(20.0, abs=0.01)


def _strong_sip_header(ra, dec):
    """TAN-SIP header whose quadratic terms diverge well outside the frame."""
    header = make_tan_header(ra, dec)
    header["CTYPE1"] = "RA---TAN-SIP"
    header["CTYPE2"] = "DEC--TAN-SIP"
    header["A_ORDER"] = 2
    header["B_ORDER"] = 2
    for i in range(3):
        for j in range(3 - i):
            header[f"A_{i}_{j}"] = 0.0
            header[f"B_{i}_{j}"] = 0.0
    header["A_2_0"] = 2.0e-4
    header["B_0_2"] = -1.5e-4
    return header


def test_sip_distortion_is_applied_and_round_trips():
    header = _strong_sip_header(SIRIUS_RA, SIRIUS_DEC)
    wcs = matching._load_wcs(header)
    ra, dec = SIRIUS_RA + 2.0, SIRIUS_DEC + 1.0
    x, y = matching._sky_to_image(wcs, ra, dec)
    # wcs_world2pix skips SIP, so a real distortion term moves the pixel.
    bare_x, bare_y = wcs.wcs_world2pix(ra, dec, 0)
    assert abs(float(x) - float(np.asarray(bare_x))) > 0.05 or abs(float(y) - float(np.asarray(bare_y))) > 0.05
    back_ra, back_dec = matching._image_to_sky(wcs, float(x), float(y))
    again_x, again_y = matching._sky_to_image(wcs, float(back_ra), float(back_dec))
    assert float(again_x) == pytest.approx(float(x), abs=0.01)
    assert float(again_y) == pytest.approx(float(y), abs=0.01)


def test_sip_off_frame_stars_do_not_abort_the_projection():
    # The safety net, past the angular pre-filter. A star far from the field
    # makes the SIP iteration diverge; the field center must still land on CRPIX.
    wcs = matching._load_wcs(_strong_sip_header(SIRIUS_RA, SIRIUS_DEC))
    x, y = matching._sky_to_image(wcs, [SIRIUS_RA, 0.0], [SIRIUS_DEC, 80.0])
    assert float(x[0]) == pytest.approx((WIDTH - 1) / 2, abs=0.01)
    assert float(y[0]) == pytest.approx((HEIGHT - 1) / 2, abs=0.01)
    assert not (np.isfinite(x[1]) and 0.0 <= float(x[1]) < WIDTH and 0.0 <= float(y[1]) < HEIGHT)


def test_strong_sip_omits_a_catalog_star_far_outside_the_frame():
    # Polaris is in the catalog and far from this Sirius field. Projecting it
    # through these SIP terms diverges; it must not crash the match or be drawn.
    result = matching.match_stars(_strong_sip_header(SIRIUS_RA, SIRIUS_DEC), WIDTH, HEIGHT, [])
    hips = {star["hip"] for star in result["stars"]}
    assert SIRIUS_HIP in hips
    assert POLARIS_HIP not in hips
    assert all(0 <= star["x"] < WIDTH and 0 <= star["y"] < HEIGHT for star in result["stars"])


def test_fits_pixels_are_one_based_and_y_is_not_flipped():
    header = make_tan_header(SIRIUS_RA, SIRIUS_DEC)
    wcs = matching._load_wcs(header)
    # CRPIX is FITS 1-based. origin=0 subtracts that one pixel and does not mirror y.
    x, y = matching._sky_to_image(wcs, header["CRVAL1"], header["CRVAL2"])
    assert float(x) == pytest.approx(header["CRPIX1"] - 1, abs=1e-6)
    assert float(y) == pytest.approx(header["CRPIX2"] - 1, abs=1e-6)
    ra, dec = wcs.all_pix2world(10.0, 20.0, 0)
    ra_fits, dec_fits = wcs.all_pix2world(11.0, 21.0, 1)
    assert float(ra) == pytest.approx(float(ra_fits), abs=1e-9)
    assert float(dec) == pytest.approx(float(dec_fits), abs=1e-9)
    flipped_ra, flipped_dec = wcs.all_pix2world(10.0, header["IMAGEH"] - 1 - 20.0, 0)
    assert abs(float(flipped_dec) - float(dec)) > 0.01


def test_source_array_accepts_a_numpy_array():
    empty = matching._source_array(np.zeros((0, 2)))
    assert empty.shape == (0, 2)
    rows = matching._source_array(np.array([[1.5, 2.5], [3.0, 4.0]]))
    assert rows.tolist() == [[1.5, 2.5], [3.0, 4.0]]


def test_star_outside_the_frame_is_excluded():
    result = matching.match_stars(make_tan_header(SIRIUS_RA, SIRIUS_DEC), WIDTH, HEIGHT, [])
    assert all(star["hip"] != POLARIS_HIP for star in result["stars"])
    assert all(0 <= star["x"] < WIDTH and 0 <= star["y"] < HEIGHT for star in result["stars"])


def test_axy_source_missing_from_corr_is_detected():
    # corr.fits is only the solver's matched pairs. A visible star can be in the
    # .axy extraction and absent from corr; matching on corr would call it a ghost.
    header = make_tan_header(SIRIUS_RA, SIRIUS_DEC)
    placed = matching.match_stars(header, WIDTH, HEIGHT, [])
    sirius = next(star for star in placed["stars"] if star["hip"] == SIRIUS_HIP)
    axy = _axy_hdul([(sirius["x"] + 1.0, sirius["y"] + 1.0, 800.0)])
    sources = sources_from_axy(axy)
    detected = matching.match_stars(header, WIDTH, HEIGHT, sources)
    sirius_matched = next(star for star in detected["stars"] if star["hip"] == SIRIUS_HIP)
    assert sirius_matched["detected"] is True

    corr_only = [{"x": 5.0, "y": 5.0}]
    assert abs(sirius["x"] - 5.0) > 4 and abs(sirius["y"] - 5.0) > 4
    missed = matching.match_stars(header, WIDTH, HEIGHT, corr_only)
    sirius_missed = next(star for star in missed["stars"] if star["hip"] == SIRIUS_HIP)
    assert sirius_missed["detected"] is False


def _axy_hdul(rows):
    """rows are (x_fits, y_fits, flux), the 1-based columns in an .axy file."""
    values = np.array(rows, dtype=float).reshape(-1, 3)
    columns = [
        fits.Column(name=name, format="D", array=values[:, index])
        for index, name in enumerate(["X", "Y", "FLUX"])
    ]
    return fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)])


def test_one_source_matches_at_most_one_star():
    # One degree per pixel packs many catalog stars inside the match radius.
    header = make_tan_header(SIRIUS_RA, SIRIUS_DEC, scale_deg_per_px=1.0, width=40, height=40)
    placed = matching.match_stars(header, 40, 40, [])
    sirius = next(star for star in placed["stars"] if star["hip"] == SIRIUS_HIP)
    crowded = [
        star for star in placed["stars"]
        if math_hypot(star["x"] - sirius["x"], star["y"] - sirius["y"]) <= 4.0
    ]
    assert len(crowded) > 1
    result = matching.match_stars(header, 40, 40, [{"x": sirius["x"], "y": sirius["y"]}])
    detected = [star for star in result["stars"] if star["detected"]]
    assert [star["hip"] for star in detected] == [SIRIUS_HIP]


def test_orion_lines_follow_the_overlay_shape():
    header = make_tan_header(88.792935, 7.407064, scale_deg_per_px=0.08, width=600, height=600)
    result = matching.match_stars(header, 600, 600, [])
    orion = next(figure for figure in result["constellations"] if figure["name"] == "Orion")
    assert orion["lines"]
    assert 0 <= orion["label"]["x"] < 600
    assert 0 <= orion["label"]["y"] < 600
    for segment in orion["lines"]:
        assert len(segment) == 4


def math_hypot(dx, dy):
    return (dx * dx + dy * dy) ** 0.5


# Achernar never rises from Buffalo (dec -57, latitude 43).
ACHERNAR_HIP = 7588
ACHERNAR_RA = 24.4283
ACHERNAR_DEC = -57.2368
MIZAR_HIP = 65378
ALCOR_HIP = 65477
DUBHE_HIP = 54061
KOCHAB_HIP = 72607
BUFFALO = (43.0, -78.79, "2026-11-08T05:00:00Z")


def test_a_star_below_the_horizon_is_left_out_of_the_overlay():
    header = make_tan_header(ACHERNAR_RA, ACHERNAR_DEC, scale_deg_per_px=0.02, width=200, height=200)
    plain = matching.match_stars(header, 200, 200, [])
    assert any(star["hip"] == ACHERNAR_HIP for star in plain["stars"])

    hidden = matching.match_stars(header, 200, 200, [], lat=BUFFALO[0], lon=BUFFALO[1], taken_at=BUFFALO[2])
    assert hidden["stars"] == []
    assert hidden["constellations"] == []
    assert hidden["stats"]["catalog_in_frame"] == 0


def test_mizar_companion_cannot_take_its_detection():
    catalog = matching.load_stars()
    mizar = next(star for star in catalog if star["hip"] == MIZAR_HIP)
    companion = min(
        (star for star in catalog if star is not mizar),
        key=lambda star: _sep_arcsec(mizar, star),
    )
    assert _sep_arcsec(mizar, companion) < 60
    assert companion["mag"] > mizar["mag"]
    header = make_tan_header(mizar["ra_deg"], mizar["dec_deg"], scale_deg_per_px=0.02)
    wcs = matching._load_wcs(header)
    cx, cy = matching._sky_to_image(wcs, companion["ra_deg"], companion["dec_deg"])
    result = matching.match_stars(header, WIDTH, HEIGHT, [{"x": float(np.ravel(cx)[0]), "y": float(np.ravel(cy)[0])}])
    by_hip = {star["hip"]: star for star in result["stars"]}
    assert by_hip[MIZAR_HIP]["detected"] is True
    assert companion["id"] not in {star["id"] for star in result["stars"]}
    assert by_hip[ALCOR_HIP]["hip"] == ALCOR_HIP


@pytest.mark.parametrize("hip", [DUBHE_HIP, KOCHAB_HIP])
def test_bright_dipper_stars_match_past_the_old_four_pixel_radius(hip):
    star = next(item for item in matching.load_stars() if item["hip"] == hip)
    header = make_tan_header(star["ra_deg"], star["dec_deg"], scale_deg_per_px=0.02)
    placed = matching.match_stars(header, WIDTH, HEIGHT, [])
    target = next(item for item in placed["stars"] if item["hip"] == hip)
    # 12 px is outside the old 4 px radius and outside the strict 8 px radius.
    result = matching.match_stars(header, WIDTH, HEIGHT, [{"x": target["x"] + 12.0, "y": target["y"]}])
    matched = next(item for item in result["stars"] if item["hip"] == hip)
    assert matched["detected"] is True


def test_a_faint_star_does_not_get_the_wide_radius():
    matched = matching._assign_sources(
        np.array([0.0, 100.0]),
        np.array([0.0, 0.0]),
        np.array([1.8, 5.5]),
        np.array([[12.0, 0.0], [112.0, 0.0]]),
        8.0,
    )
    assert matched.tolist() == [True, False]


def test_a_star_on_bright_ground_is_left_out():
    header = make_tan_header(SIRIUS_RA, SIRIUS_DEC)
    dark = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    ground = np.full((HEIGHT, WIDTH, 3), 220, dtype=np.uint8)
    on_sky = matching.match_stars(header, WIDTH, HEIGHT, [], image=dark)
    on_ground = matching.match_stars(header, WIDTH, HEIGHT, [], image=ground)
    assert any(star["hip"] == SIRIUS_HIP for star in on_sky["stars"])
    assert all(star["hip"] != SIRIUS_HIP for star in on_ground["stars"])


def _sep_arcsec(a, b):
    dra = np.radians((a["ra_deg"] - b["ra_deg"]) * np.cos(np.radians(a["dec_deg"])))
    ddec = np.radians(a["dec_deg"] - b["dec_deg"])
    return float(np.degrees(np.hypot(dra, ddec)) * 3600.0)


@pytest.mark.skipif(
    not (WCS_FIXTURE.exists() and CORR_FIXTURE.exists()),
    reason=(
        "optional real-photo check. From a solved nova.astrometry.net job, save "
        "wcs_file/JOBID as backend/tests/fixtures/wcs.fits and corr_file/JOBID as "
        "backend/tests/fixtures/corr.fits (*.fits is gitignored)"
    ),
)
def test_real_photo_corr_projects_onto_field_pixels():
    """Index stars in corr.fits land on the field pixels from that same file.

    corr field_x/field_y are 1-based FITS pixels. solver.fits_xy_to_image shifts
    them to image pixels. A y-flip would throw the median off by a large fraction
    of the frame; the solver's own photos sit within a couple of pixels.
    """
    from app.solver import fits_xy_to_image

    wcs = matching._load_wcs(WCS_FIXTURE)
    with fits.open(CORR_FIXTURE) as hdul:
        table = hdul[1].data
        columns = {name.lower(): name for name in table.columns.names}
        field_x = np.asarray(table[columns["field_x"]], dtype=float)
        field_y = np.asarray(table[columns["field_y"]], dtype=float)
        index_ra = np.asarray(table[columns["index_ra"]], dtype=float)
        index_dec = np.asarray(table[columns["index_dec"]], dtype=float)
    image_x, image_y = fits_xy_to_image(field_x, field_y)
    projected_x, projected_y = matching._sky_to_image(wcs, index_ra, index_dec)
    distance = np.hypot(projected_x - image_x, projected_y - image_y)
    assert float(np.median(distance)) < 5.0
