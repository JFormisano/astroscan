"""The step between the solver and the results page: solver block in, drawable result out.

The synthetic photo is centred on Polaris (HIP 11767), so we know exactly where one bright catalog
star must land: the middle of the frame. That makes "detected" vs "ghost" checkable without a real
photo; the real-photo version of these checks runs in the Docker test run.
"""
import json

import pytest
from astropy.io import fits

from app import conditions, matching, pipeline, solver
from tests.conftest import make_photo

W, H = 1000, 800
POLARIS_RA, POLARIS_DEC = 37.94625, 89.264109
NIGHT = "2026-11-08T05:00:00+00:00"  # midnight in Buffalo
NOON = "2026-11-07T17:00:00+00:00"  # noon in Buffalo


def wcs_header(ra=POLARIS_RA, dec=POLARIS_DEC, deg_per_px=0.05) -> dict:
    h = fits.Header()
    h["WCSAXES"] = 2
    h["CTYPE1"], h["CTYPE2"] = "RA---TAN", "DEC--TAN"
    h["CRPIX1"], h["CRPIX2"] = (W + 1) / 2, (H + 1) / 2  # FITS 1-based: the middle of the image
    h["CRVAL1"], h["CRVAL2"] = ra, dec
    h["CD1_1"], h["CD1_2"], h["CD2_1"], h["CD2_2"] = -deg_per_px, 0.0, 0.0, deg_per_px
    return {k: h[k] for k in h}


def solver_block(sources=()):
    return {
        "solver_used": "local",
        "wcs": wcs_header(),
        "sources": list(sources),
        "stats": {
            "image_width_px": W,
            "image_height_px": H,
            "stars_detected": len(sources),
            "stars_matched": 21,  # the SOLVER's count
            "field_width_deg": 40.0,
            "field_height_deg": 31.0,
            "ra_center": POLARIS_RA,
            "dec_center": POLARIS_DEC,
            "solve_seconds": 5.5,
            "log_odds": 120.0,
        },
    }


CENTRE = ((W - 1) / 2, (H - 1) / 2)


def run(block, taken=NIGHT, **kw):
    return pipeline.analyze(block, lat=43.0, lon=-78.79, taken_at_utc=taken, image_url="/img.jpg", **kw)


def polaris(result):
    return next(s for s in result["stars"] if s["name"] == "Polaris")


# --- stars and constellations -------------------------------------------------------------


def test_polaris_lands_in_the_middle_of_the_frame_and_is_detected_when_a_source_is_there():
    result = run(solver_block([{"x": CENTRE[0], "y": CENTRE[1], "flux": 900.0}]))
    star = polaris(result)
    assert (star["x"], star["y"]) == pytest.approx(CENTRE, abs=0.6)
    assert star["detected"] is True and star["mag"] == pytest.approx(1.97)


def test_a_catalog_star_with_no_source_nearby_is_a_ghost():
    far = {"x": 50.0, "y": 50.0, "flux": 10.0}  # a source, but nowhere near Polaris
    assert polaris(run(solver_block([far])))["detected"] is False


def test_result_has_the_demo_shape_fields_the_page_reads():
    result = run(solver_block())
    assert result["image"] == {"url": "/img.jpg", "width": W, "height": H}
    assert result["taken_at_utc"] == NIGHT and result["location"] == {"lat": 43.0, "lon": -78.79}
    assert len(result["stars"]) > 50 and all({"x", "y", "mag", "detected"} <= set(s) for s in result["stars"])
    assert result["constellations"] and all({"name", "label", "lines"} <= set(c) for c in result["constellations"])
    assert result["score"]["value"] in range(1, 10) and 0 <= result["score"]["pct_lost"] <= 100
    json.dumps(result)  # it is stored as JSON


def test_everything_the_solver_returned_is_kept():
    block = solver_block([{"x": 5.0, "y": 6.0, "flux": 1.0}])
    result = run(block)
    assert result["solver_used"] == "local" and result["wcs"] == block["wcs"] and result["sources"] == block["sources"]


def test_the_input_is_not_modified():
    block = solver_block()
    before = json.dumps(block)
    run(block)
    assert json.dumps(block) == before


# --- stats --------------------------------------------------------------------------------


def test_stats_matched_means_catalog_stars_found_and_the_solvers_count_is_kept_separately():
    result = run(solver_block([{"x": CENTRE[0], "y": CENTRE[1], "flux": 900.0}]))
    stats = result["stats"]
    assert stats["stars_matched"] == sum(s["detected"] for s in result["stars"]) >= 1  # matching's meaning
    assert stats["solver_stars_matched"] == 21  # the solver's own count
    assert stats["catalog_in_frame"] == len(result["stars"])
    assert stats["stars_detected"] == 1 and stats["solve_seconds"] == 5.5 and stats["log_odds"] == 120.0
    assert stats["image_width_px"] == W


# --- conditions -> warnings, planets ------------------------------------------------------


def test_a_midnight_photo_has_no_twilight_warning():
    result = run(solver_block(), taken=NIGHT)
    assert all(w["type"] != "twilight" for w in result["warnings"])
    assert result["conditions"]["flags"]["twilight"] is False and "planets" not in result["conditions"]


def test_a_noon_photo_gets_a_twilight_warning():
    assert {"type": "twilight"} in run(solver_block(), taken=NOON)["warnings"]


def test_warning_list_is_a_rename_of_the_flags(monkeypatch):
    monkeypatch.setattr(
        conditions,
        "evaluate_conditions",
        lambda *a, **k: {
            "flags": {"twilight": False, "moon_up": True, "low_altitude": True},
            "moon_illumination_pct": 87.4,
            "planets": [],
        },
    )
    assert run(solver_block())["warnings"] == [
        {"type": "moon", "moon_illumination_pct": 87},
        {"type": "low_altitude"},
    ]


def planet(name, ra, dec, up=True):
    return {"name": name, "ra_deg": ra, "dec_deg": dec, "alt_deg": 40.0 if up else -10.0,
            "az_deg": 90.0, "magnitude": -2.0, "above_horizon": up}


def test_planets_become_pixel_positions_and_only_visible_ones_in_frame_are_kept(monkeypatch):
    planets = [
        planet("Jupiter", POLARIS_RA, POLARIS_DEC),  # at the field centre
        planet("Venus", POLARIS_RA, POLARIS_DEC, up=False),  # in frame but below the horizon
        planet("Mars", POLARIS_RA + 180, -30.0),  # on the other side of the sky
    ]
    monkeypatch.setattr(
        conditions,
        "evaluate_conditions",
        lambda *a, **k: {"flags": {}, "moon_illumination_pct": 10.0, "planets": planets},
    )
    out = run(solver_block())["planets"]
    assert [p["name"] for p in out] == ["Jupiter"]
    assert (out[0]["x"], out[0]["y"]) == pytest.approx(CENTRE, abs=0.6)
    assert out[0]["mag"] == -2.0 and out[0]["above_horizon"] is True


# --- it never turns a solved photo into a failure -------------------------------------------


def test_stub_results_pass_through_untouched():
    stub = {"stub": True, "solver_used": "stub"}
    assert run(stub) == stub


def test_matching_crash_keeps_the_solver_output(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bad wcs")

    monkeypatch.setattr(matching, "match_stars", boom)
    result = run(solver_block())
    assert result["wcs"] and result["image"]["width"] == W and "stars" not in result


def test_conditions_crash_keeps_the_stars(monkeypatch):
    def boom(*a, **k):
        raise ValueError("naive timestamp")

    monkeypatch.setattr(conditions, "evaluate_conditions", boom)
    result = run(solver_block())
    assert len(result["stars"]) > 50 and "warnings" not in result and "planets" not in result


def test_garbage_wcs_does_not_raise():
    block = solver_block()
    block["wcs"] = {"CTYPE1": "nonsense"}
    assert "stars" not in run(block)


def test_reports_the_matching_step():
    steps = []
    run(solver_block(), on_step=steps.append)
    assert steps == ["matching", "scoring"]


def test_score_uses_the_matched_stars_and_the_photos_exif(monkeypatch):
    seen = {}

    def fake_score(match_result, cond, exif):
        seen.update(match_result=match_result, cond=cond, exif=exif)
        return {"value": 6, "limiting_mag": 4.5, "pct_lost": 60.0, "confidence": "low"}

    monkeypatch.setattr(pipeline.scoring, "score_sky", fake_score)
    result = run(solver_block(), exif={"iso": 800})
    assert result["score"]["value"] == 6
    assert seen["exif"] == {"iso": 800} and "flags" in seen["cond"]
    assert seen["match_result"]["stars"] is result["stars"] and "stars_matched" in seen["match_result"]["stats"]


def test_a_scoring_crash_keeps_everything_else(monkeypatch):
    monkeypatch.setattr(pipeline.scoring, "score_sky", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    result = run(solver_block())
    assert "score" not in result and result["stars"] and "planets" in result


def test_no_score_when_there_are_too_few_catalog_stars_to_judge(monkeypatch):
    monkeypatch.setattr(pipeline.scoring, "score_sky", lambda *a: {"value": None, "limiting_mag": None})
    assert "score" not in run(solver_block())


# --- inside the upload flow ----------------------------------------------------------------


def test_uploaded_photo_comes_back_with_stars_from_the_pipeline(client, store, monkeypatch):
    seen_steps = []
    real_update = store.update_job

    def spy(job_id, fields):
        if "step" in fields:
            seen_steps.append(fields["step"])
        real_update(job_id, fields)

    monkeypatch.setattr(store, "update_job", spy)
    monkeypatch.setattr(solver, "solve", lambda *a, **k: solver_block([{"x": CENTRE[0], "y": CENTRE[1], "flux": 9.0}]))
    res = client.post(
        "/api/measurements",
        files={"image": ("sky.jpg", make_photo(), "image/jpeg")},
        data={"lat": "43.0008", "lon": "-78.7897"},
    )
    body = client.get(f"/api/measurements/{res.json()['job_id']}").json()
    assert body["status"] == "solved"
    assert polaris(body["result"])["detected"] is True
    assert body["result"]["image"]["url"] == body["image_url"]
    assert body["result"]["location"] == {"lat": 43.0, "lon": -78.79}
    assert body["result"]["taken_at_utc"].startswith("2026-11-08T02:30:05")  # from the photo's EXIF
    assert "matching" in seen_steps


def test_a_pipeline_crash_still_leaves_a_solved_job(client, monkeypatch):
    monkeypatch.setattr(solver, "solve", lambda *a, **k: solver_block())
    monkeypatch.setattr(matching, "match_stars", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    res = client.post(
        "/api/measurements",
        files={"image": ("sky.jpg", make_photo(), "image/jpeg")},
        data={"lat": "43.0008", "lon": "-78.7897"},
    )
    body = client.get(f"/api/measurements/{res.json()['job_id']}").json()
    assert body["status"] == "solved" and body["result"]["wcs"] and "stars" not in body["result"]


