"""Real solve-field runs on real sky photos. Skipped unless solve-field and the index files exist,
i.e. run these inside the Docker image (see README, "Run the solver in Docker").

The photos are openly licensed Wikimedia Commons images kept OUT of git (test_photos/, mounted at
TEST_PHOTOS_DIR). Each shows the Big Dipper, whose seven stars have well-known J2000 positions, so
we can check the solve against the sky itself rather than against our own code.
"""
import math
import os
from pathlib import Path

import pytest
from astropy.wcs import WCS

from app import solver

PHOTOS = Path(os.environ.get("TEST_PHOTOS_DIR") or Path(__file__).resolve().parents[2] / "test_photos")

# (RA, Dec) in degrees, J2000.
BIG_DIPPER = {
    "Dubhe": (165.932, 61.751),
    "Merak": (165.460, 56.382),
    "Phecda": (178.458, 53.695),
    "Megrez": (183.857, 57.033),
    "Alioth": (193.507, 55.960),
    "Mizar": (200.981, 54.925),
    "Alkaid": (206.885, 49.313),
}

pytestmark = pytest.mark.skipif(not solver.local_available(), reason="solve-field / index files not installed")

PHOTO_NAMES = ["dunes_2048.jpg", "sandvik_2048.jpg"]


@pytest.fixture(scope="module", params=PHOTO_NAMES)
def solved(request):
    path = PHOTOS / request.param
    if not path.exists():
        pytest.skip(f"{path} not found (test photos are not committed)")
    steps = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SOLVER_MODE", "local")
        result = solver.solve(path, 43.0, -78.79, None, on_step=steps.append)
    return path, result, steps


def test_real_photo_solves_with_enough_evidence(solved):
    _, result, steps = solved
    stats = result["stats"]
    assert result["solver_used"] == "local"
    assert stats["stars_matched"] >= solver.MIN_MATCHED_STARS
    assert stats["log_odds"] >= solver.MIN_LOG_ODDS
    assert steps == ["detecting", "solving"]
    print(f"\n{solved[0].name}: {stats['solve_seconds']}s, matched {stats['stars_matched']}, field "
          f"{stats['field_width_deg']}x{stats['field_height_deg']} deg, {stats['stars_detected']} sources")


def test_field_is_a_plausible_phone_or_camera_view(solved):
    stats = solved[1]["stats"]
    assert 20 < stats["field_width_deg"] < 100 and 20 < stats["field_height_deg"] < 100
    assert 140 < stats["ra_center"] < 240 and 30 < stats["dec_center"] < 80  # Big Dipper region


def test_big_dipper_stars_land_on_detected_stars(solved):
    """Known answer: project the seven Big Dipper stars through the returned WCS using image pixels
    (origin=0, no flip). Each one inside the frame must have a detected star within a few pixels.
    A flipped axis, an off-by-one or a broken distortion fit would fail this."""
    _, result, _ = solved
    stats = result["stats"]
    w, h = stats["image_width_px"], stats["image_height_px"]
    # Rebuild the WCS from the returned dict, the way matching.py will.
    from astropy.io import fits

    wcs = WCS(fits.Header({k: v for k, v in result["wcs"].items()}))
    sources = result["sources"]
    inside, hits = [], []
    for name, (ra, dec) in BIG_DIPPER.items():
        x, y = (float(v) for v in wcs.all_world2pix(ra, dec, 0))
        if 5 < x < w - 5 and 5 < y < h - 5:
            inside.append(name)
            nearest = min(math.hypot(s["x"] - x, s["y"] - y) for s in sources)
            if nearest <= 10:
                hits.append(name)
    assert len(inside) >= 4, f"expected most of the Big Dipper in frame, got {inside}"
    assert len(hits) >= len(inside) - 1, f"in frame: {inside}; on a detected star: {hits}"


def test_sources_sit_on_bright_pixels_not_a_mirrored_image(solved):
    """Pixel-convention check on the photo itself: the brightest detected stars must be on bright
    pixels. Mirroring y (the classic FITS mistake) puts them on dark sky."""
    import numpy as np
    from PIL import Image

    path, result, _ = solved
    img = np.asarray(Image.open(path).convert("L"), dtype=float)
    top = result["sources"][:40]
    under = [img[int(round(s["y"])), int(round(s["x"]))] for s in top]
    assert np.mean(under) > 3 * np.median(img)


def test_blank_sky_fails_fast_with_a_star_count(monkeypatch):
    import tempfile

    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "blank.jpg"
        Image.new("RGB", (1600, 1200), (8, 8, 12)).save(path)
        monkeypatch.setenv("SOLVER_MODE", "local")
        with pytest.raises(solver.SolveFailed) as e:
            solver.solve(path, 43.0, -78.79, None)
    assert e.value.code == "too_few_stars" and e.value.detected_stars is not None


def test_full_chain_names_the_big_dipper_stars_and_marks_them_detected(solved):
    """Solve -> analyze on a real photo: the pipeline's own output (what the page draws) must carry
    the Big Dipper's named stars at the right pixels with a detection on top of them."""
    from app import pipeline

    _, result, _ = solved
    out = pipeline.analyze(
        result, lat=43.0, lon=-78.79, taken_at_utc="2026-11-08T05:00:00+00:00", image_url="/x.jpg"
    )
    assert out["stars"] and out["constellations"] and "warnings" in out
    named = {s["name"]: s for s in out["stars"] if s["name"] in BIG_DIPPER}
    assert len(named) >= 4, f"Big Dipper stars found in the pipeline output: {sorted(named)}"
    detected = [n for n, s in named.items() if s["detected"]]
    assert len(detected) >= len(named) - 1, f"named {sorted(named)}, detected {sorted(detected)}"
    # the pipeline's pixel for a named star equals where the WCS projects its catalog position
    from astropy.io import fits

    wcs = WCS(fits.Header(result["wcs"]))
    for name, star in named.items():
        x, y = (float(v) for v in wcs.all_world2pix(*BIG_DIPPER[name], 0))
        assert math.hypot(star["x"] - x, star["y"] - y) < 3, name
