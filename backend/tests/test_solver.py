"""Solver tests that need neither solve-field nor the network (those run in Docker; see README)."""
import io
import json
import math
import time

import httpx
import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

from app import solver

W, H = 1600, 1200


# --- helpers ------------------------------------------------------------------------------


def make_wcs_header(ra=83.8, dec=-5.4, scale_deg_per_px=0.04, w=W, h=H) -> fits.Header:
    """A plain TAN solution centred in the image, FITS frame, like solve-field's .wcs."""
    hdr = fits.Header()
    hdr["WCSAXES"] = 2
    hdr["CTYPE1"], hdr["CTYPE2"] = "RA---TAN", "DEC--TAN"
    hdr["CRPIX1"], hdr["CRPIX2"] = (w + 1) / 2, (h + 1) / 2
    hdr["CRVAL1"], hdr["CRVAL2"] = ra, dec
    hdr["CD1_1"], hdr["CD1_2"], hdr["CD2_1"], hdr["CD2_2"] = -scale_deg_per_px, 0.0, 0.0, scale_deg_per_px
    hdr["IMAGEW"], hdr["IMAGEH"] = w, h
    return hdr


def to_bytes(hdul) -> bytes:
    buf = io.BytesIO()
    hdul.writeto(buf)
    return buf.getvalue()


def wcs_bytes(**kw) -> bytes:
    return to_bytes(fits.HDUList([fits.PrimaryHDU(header=make_wcs_header(**kw))]))


def axy_bytes(stars) -> bytes:
    """stars: (x_fits, y_fits, flux) rows -> FITS bytes with a table like solve-field's .axy."""
    arr = np.array(stars, dtype=float).reshape(-1, 3)
    cols = [fits.Column(name=n, format="D", array=arr[:, i]) for i, n in enumerate(["X", "Y", "FLUX"])]
    return to_bytes(fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(cols)]))


def corr_bytes(n) -> bytes:
    col = fits.Column(name="index_id", format="J", array=np.arange(n))
    return to_bytes(fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns([col])]))


STARS = [(100 + 10 * i, 50 + 7 * i, 1000 - i) for i in range(30)]


@pytest.fixture
def photo_path(tmp_path):
    path = tmp_path / "sky.jpg"
    Image.new("RGB", (W, H), (3, 3, 10)).save(path)
    return path


# --- pure helpers -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "focal_35,w,h,expected_width_deg",
    [
        (26, 1600, 1200, 69.4),  # typical phone main camera, landscape: 2*atan(18/26)
        (26, 1200, 1600, 49.6),  # same lens, portrait: 2*atan(12/26)
        (50, 1600, 1200, 39.6),
    ],
)
def test_scale_range_uses_lopsided_window_around_exif_estimate(focal_35, w, h, expected_width_deg):
    low, high = solver.scale_range_deg(w, h, focal_35)
    assert low == pytest.approx(expected_width_deg * 0.35, abs=0.1)
    assert high == pytest.approx(min(120, expected_width_deg * 1.2), abs=0.1)


def test_scale_range_without_exif_is_wide():
    for missing in (None, 0, -5):
        assert solver.scale_range_deg(1600, 1200, missing) == (10.0, 100.0)


def test_scale_range_is_clamped():
    low, high = solver.scale_range_deg(1600, 1200, 8)  # ultra wide: 2*atan(18/8) = 132 deg
    assert high <= 120 and low >= 2
    low, high = solver.scale_range_deg(1600, 1200, 1000)  # long telephoto: ~2 deg
    assert low >= 2 and high > low


def test_fits_pixel_numbers_to_image_pixels_is_a_one_pixel_shift_and_no_flip():
    # astrometry.net's first pixel is (1, 1); ours is (0, 0). Its y points down like the image's.
    assert solver.fits_xy_to_image(1, 1) == (0, 0)
    assert solver.fits_xy_to_image(W, H) == (W - 1, H - 1)
    assert solver.fits_xy_to_image(1, H) == (0, H - 1)  # bottom-left stays bottom-left


def test_pixel_conversion_round_trips():
    for x, y in [(0, 0), (12.5, 700.25), (W - 1, H - 1)]:
        assert solver.fits_xy_to_image(*solver.image_xy_to_fits(x, y)) == pytest.approx((x, y))


def test_image_pixels_go_straight_into_the_wcs_with_origin_zero():
    """Known answer: the image centre is the reference point, and image pixels need no flip or shift
    before going into the WCS (astropy origin=0). Direction is whatever the WCS says."""
    hdr = make_wcs_header(ra=83.8, dec=-5.4)
    wcs = WCS(hdr)
    ra, dec = wcs.all_pix2world((W - 1) / 2, (H - 1) / 2, 0)
    assert (float(ra), float(dec)) == pytest.approx((83.8, -5.4), abs=1e-6)
    _, dec_low_y = wcs.all_pix2world((W - 1) / 2, 10, 0)  # small image y
    _, dec_high_y = wcs.all_pix2world((W - 1) / 2, H - 10, 0)  # large image y
    assert float(dec_high_y) > float(dec_low_y)  # follows the WCS exactly; no hidden flip


def test_field_stats_match_a_known_geometry():
    stats = solver.field_stats(make_wcs_header(scale_deg_per_px=0.04), W, H)
    # TAN projection: a 64 deg flat-grid width is 2*atan(tan(32 deg)) of true sky angle
    flat_half_deg = 0.04 * W / 2
    expected_w = 2 * math.degrees(math.atan(math.radians(flat_half_deg)))
    assert stats["field_width_deg"] == pytest.approx(expected_w, abs=0.5)
    assert stats["field_height_deg"] < stats["field_width_deg"]
    assert stats["pixel_scale_arcsec"] == pytest.approx(144, abs=1)
    assert stats["ra_center"] == pytest.approx(83.8, abs=0.01)
    assert stats["dec_center"] == pytest.approx(-5.4, abs=0.01)


def test_sources_are_brightest_first_in_image_pixels():
    with fits.open(io.BytesIO(axy_bytes([(1, 1, 5.0), (W, H, 50.0)]))) as hdul:
        sources = solver.sources_from_axy(hdul)
    assert sources[0] == {"x": W - 1, "y": H - 1, "flux": 50.0}
    assert sources[1] == {"x": 0, "y": 0, "flux": 5.0}


def test_header_to_dict_is_json_safe():
    hdr = make_wcs_header()
    hdr["COMMENT"] = "dropped"
    d = solver.header_to_dict(hdr)
    json.dumps(d)
    assert "COMMENT" not in d and d["CTYPE1"] == "RA---TAN" and d["CRVAL1"] == 83.8


def test_every_failure_has_a_plain_message_and_next_step():
    for err in (
        solver.too_few_stars(3),
        solver.no_match(40),
        solver.solve_timeout(40),
        solver.solver_unavailable(),
        solver.solve_error(),
    ):
        assert err.message and err.next_step and err.code
    assert solver.too_few_stars(3).detected_stars == 3
    assert "light pollution" in solver.too_few_stars(3).next_step


def test_build_output_to_result_shape():
    with fits.open(io.BytesIO(axy_bytes(STARS))) as hdul:
        out = solver.build_output("local", make_wcs_header(), hdul, W, H, 21)
    result = out.to_result(1.234)
    assert result["solver_used"] == "local"
    assert result["wcs"]["CRVAL1"] == 83.8
    assert len(result["sources"]) == 30
    assert result["stats"]["stars_detected"] == 30 and result["stats"]["stars_matched"] == 21
    assert result["stats"]["solve_seconds"] == 1.23
    assert result["stats"]["field_width_deg"] > 0
    json.dumps(result)


def test_result_caps_returned_sources():
    many = [(i % W + 1, i // W + 1, float(i)) for i in range(solver.MAX_SOURCES_RETURNED + 200)]
    with fits.open(io.BytesIO(axy_bytes(many))) as hdul:
        out = solver.build_output("local", make_wcs_header(), hdul, W, H, 20)
    assert out.stars_detected == solver.MAX_SOURCES_RETURNED + 200
    assert len(out.to_result(1)["sources"]) == solver.MAX_SOURCES_RETURNED


# --- nova.astrometry.net client (mocked server) -------------------------------------------


class FakeNova:
    """Just enough of nova.astrometry.net: login, upload, submission, job and result files."""

    def __init__(self, *, login_ok=True, job_statuses=("solving", "success"), matched=21):
        self.login_ok = login_ok
        self.job_statuses = list(job_statuses)
        self.matched = matched
        self.uploads: list[dict] = []
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path == "/api/login":
            if not self.login_ok:
                return httpx.Response(200, json={"status": "error", "message": "bad apikey"})
            return httpx.Response(200, json={"status": "success", "session": "sess123"})
        if path == "/api/upload":
            body = request.content
            start = body.index(b"{")
            self.uploads.append(json.loads(body[start : body.index(b"}", start) + 1]))
            return httpx.Response(200, json={"status": "success", "subid": 7})
        if path == "/api/submissions/7":
            return httpx.Response(200, json={"jobs": [None] if len(self.calls) < 6 else [42]})
        if path == "/api/jobs/42":
            status = self.job_statuses.pop(0) if len(self.job_statuses) > 1 else self.job_statuses[0]
            return httpx.Response(200, json={"status": status})
        if path == "/wcs_file/42":
            return httpx.Response(200, content=wcs_bytes())
        if path == "/axy_file/42":
            return httpx.Response(200, content=axy_bytes(STARS))
        if path == "/corr_file/42":
            return httpx.Response(200, content=corr_bytes(self.matched))
        return httpx.Response(404)


def run_nova(fake, photo_path, steps=None, scale=(20.0, 80.0)):
    client = httpx.Client(transport=httpx.MockTransport(fake))
    return solver._solve_nova(
        photo_path, W, H, scale, (steps.append if steps is not None else (lambda s: None)), http=client, sleep=lambda s: None
    )


@pytest.fixture(autouse=True)
def nova_env(monkeypatch):
    monkeypatch.setenv("ASTROMETRY_API_KEY", "test-key")
    monkeypatch.setenv("API_SOLVE_TIMEOUT_S", "30")


def test_nova_happy_path(photo_path):
    fake, steps = FakeNova(), []
    out = run_nova(fake, photo_path, steps)
    assert out.solver_used == "nova"
    assert out.stars_detected == 30 and out.stars_matched == 21
    assert out.wcs["CRVAL1"] == 83.8
    assert steps == ["detecting", "solving"]


def test_nova_upload_is_private_and_carries_scale_hint(photo_path):
    fake = FakeNova()
    run_nova(fake, photo_path, scale=(25.0, 85.5))
    sent = fake.uploads[0]
    assert sent["publicly_visible"] == "n"
    assert sent["session"] == "sess123"
    assert (sent["scale_units"], sent["scale_lower"], sent["scale_upper"]) == ("degwidth", 25.0, 85.5)
    assert sent["tweak_order"] == 3


def test_nova_sends_no_location_or_time(photo_path):
    fake = FakeNova()
    run_nova(fake, photo_path)
    blob = json.dumps(fake.uploads[0]).lower()
    for word in ("lat", "lon", "taken", "gps"):
        assert word not in blob


def test_nova_bad_key_is_unavailable_not_a_crash(photo_path):
    with pytest.raises(solver.SolveFailed) as e:
        run_nova(FakeNova(login_ok=False), photo_path)
    assert e.value.code == "solver_unavailable"


def test_nova_missing_key_is_unavailable(photo_path, monkeypatch):
    monkeypatch.delenv("ASTROMETRY_API_KEY")
    with pytest.raises(solver.SolveFailed) as e:
        run_nova(FakeNova(), photo_path)
    assert e.value.code == "solver_unavailable"


def test_nova_failed_job_is_no_match(photo_path):
    with pytest.raises(solver.SolveFailed) as e:
        run_nova(FakeNova(job_statuses=("failure",)), photo_path)
    assert e.value.code == "no_match"


def test_nova_job_that_never_finishes_times_out(photo_path, monkeypatch):
    monkeypatch.setenv("API_SOLVE_TIMEOUT_S", "0.05")
    client = httpx.Client(transport=httpx.MockTransport(FakeNova(job_statuses=("solving",))))
    with pytest.raises(solver.SolveFailed) as e:
        solver._solve_nova(photo_path, W, H, (20, 80), lambda s: None, http=client, sleep=lambda s: time.sleep(0.02))
    assert e.value.code == "solve_timeout"


def test_nova_too_few_matched_stars_is_rejected(photo_path):
    with pytest.raises(solver.SolveFailed) as e:
        run_nova(FakeNova(matched=3), photo_path)
    assert e.value.code == "no_match"


def test_nova_network_error_becomes_plain_failure(photo_path):
    def boom(request):
        raise httpx.ConnectError("dns failure for nova.astrometry.net")

    client = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(solver.SolveFailed) as e:
        solver._solve_nova(photo_path, W, H, (20, 80), lambda s: None, http=client, sleep=lambda s: None)
    assert e.value.code == "solve_failed"
    assert "dns" not in e.value.message.lower() + e.value.next_step.lower()


# --- solve() entry point ------------------------------------------------------------------


def test_stub_mode_still_works(photo_path, monkeypatch):
    monkeypatch.setenv("SOLVER_MODE", "stub")
    monkeypatch.setattr(solver, "STUB_DELAY_S", 0)
    steps = []
    result = solver.solve(photo_path, 43.0, -78.79, None, on_step=steps.append)
    assert result["solver_used"] == "stub" and steps == ["detecting", "solving"]


def test_api_mode_goes_straight_to_nova_with_scale_from_exif(photo_path, monkeypatch):
    monkeypatch.setenv("SOLVER_MODE", "api")
    seen = {}

    def fake_nova(path, w, h, scale, step, **kw):
        seen.update(w=w, h=h, scale=scale)
        with fits.open(io.BytesIO(axy_bytes(STARS))) as axy:
            return solver.build_output("nova", make_wcs_header(), axy, w, h, 20)

    monkeypatch.setattr(solver, "_solve_nova", fake_nova)
    result = solver.solve(photo_path, 43.0, -78.79, None, hints={"focal_35mm": 26})
    assert result["solver_used"] == "nova"
    assert (seen["w"], seen["h"]) == (W, H)
    assert seen["scale"][0] == pytest.approx(69.4 * 0.35, abs=0.2)
    assert result["stats"]["solve_seconds"] >= 0


def test_a_blank_photo_is_not_a_math_domain_error():
    assert math.isfinite(solver.scale_range_deg(1, 1, 26)[0])


# --- local solver stages (solve-field faked at the subprocess boundary) --------------------


def match_bytes(log_odds) -> bytes:
    col = fits.Column(name="LOGODDS", format="E", array=np.array([log_odds], dtype="f4"))
    return to_bytes(fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns([col])]))


class FakeSolveField:
    """Stands in for `_run`: writes the files solve-field / astrometry-engine would write."""

    def __init__(self, *, stars=STARS, solved=True, matched=21, log_odds=80.0, augment_rc=0, engine_rc=0,
                 engine_output="", augment_raises=None, engine_raises=None, solve_on_call=1, timeout_calls=()):
        self.stars, self.solved, self.matched, self.log_odds = stars, solved, matched, log_odds
        self.solve_on_call, self.timeout_calls = solve_on_call, set(timeout_calls)
        self.engine_calls = 0
        self.engine_windows: list[tuple[float, float, float]] = []  # (low deg, high deg, cpu limit) per engine run
        self.augment_rc, self.engine_rc, self.engine_output = augment_rc, engine_rc, engine_output
        self.augment_raises, self.engine_raises = augment_raises, engine_raises
        self.commands: list[list[str]] = []

    def __call__(self, cmd, cwd, timeout):
        self.commands.append(cmd)
        if cmd[0] == "solve-field":
            if self.augment_raises:
                raise self.augment_raises
            if self.augment_rc == 0:
                with open(cmd[cmd.index("--axy") + 1], "wb") as f:  # an absolute path inside the temp dir
                    f.write(axy_bytes(self.stars))
            return self.augment_rc, ""
        self.engine_calls += 1
        with fits.open(cmd[-1]) as axy:  # what the engine would read: scale window and CPU limit
            h = axy[0].header
            self.engine_windows.append((h["ANAPPL1"] * W / 3600, h["ANAPPU1"] * W / 3600, h["ANCLIM"]))
        if self.engine_raises:
            raise self.engine_raises
        if self.engine_calls in self.timeout_calls:
            import subprocess

            raise subprocess.TimeoutExpired("astrometry-engine", timeout)
        if self.solved and self.engine_calls >= self.solve_on_call:
            (cwd / "photo.solved").write_bytes(b"\x01")
            (cwd / "photo.wcs").write_bytes(wcs_bytes())
            (cwd / "photo.corr").write_bytes(corr_bytes(self.matched))
            (cwd / "photo.match").write_bytes(match_bytes(self.log_odds))
        return self.engine_rc, self.engine_output


def run_local(fake, photo_path, monkeypatch, steps=None, scales=None):
    monkeypatch.setattr(solver, "_run", fake)
    scales = scales or [(20.0, 80.0)]
    return solver._solve_local(photo_path, W, H, scales, (steps.append if steps is not None else (lambda s: None)))


def test_local_happy_path_reads_wcs_sources_and_match_quality(photo_path, monkeypatch):
    fake, steps = FakeSolveField(), []
    out = run_local(fake, photo_path, monkeypatch, steps)
    assert out.solver_used == "local"
    assert out.stars_detected == 30 and out.stars_matched == 21
    assert out.stats["log_odds"] == 80.0
    assert out.wcs["CRVAL1"] == 83.8
    assert steps == ["detecting", "solving"]


def test_local_commands_carry_scale_hint_and_distortion_fit(photo_path, monkeypatch):
    fake = FakeSolveField()
    run_local(fake, photo_path, monkeypatch)
    augment = fake.commands[0]
    assert augment[0] == "solve-field" and "--just-augment" in augment and "--no-plots" in augment
    assert augment[augment.index("--scale-low") + 1] == "20.00" and augment[augment.index("--scale-high") + 1] == "80.00"
    assert augment[augment.index("--tweak-order") + 1] == "3"
    assert "--crpix-center" in augment
    assert augment[augment.index("--objs") + 1] == str(solver.MAX_OBJS)
    assert fake.commands[1][0] == "astrometry-engine"


def test_local_too_few_stars_fails_before_searching(photo_path, monkeypatch):
    fake = FakeSolveField(stars=[(10, 10, 5.0)] * 3)
    with pytest.raises(solver.SolveFailed) as e:
        run_local(fake, photo_path, monkeypatch)
    assert e.value.code == "too_few_stars" and e.value.detected_stars == 3
    assert len(fake.commands) == 1  # the engine never ran


def test_local_solved_flag_with_too_few_matches_is_rejected(photo_path, monkeypatch):
    with pytest.raises(solver.SolveFailed) as e:
        run_local(FakeSolveField(matched=3), photo_path, monkeypatch)
    assert e.value.code == "no_match" and e.value.detected_stars == 30


def test_local_weak_log_odds_is_rejected(photo_path, monkeypatch):
    with pytest.raises(solver.SolveFailed) as e:
        run_local(FakeSolveField(log_odds=22.0), photo_path, monkeypatch)
    assert e.value.code == "no_match"


def test_local_exit_code_zero_without_solved_file_is_no_match(photo_path, monkeypatch):
    fake = FakeSolveField(solved=False, engine_rc=0, engine_output="Field 1 did not solve")
    with pytest.raises(solver.SolveFailed) as e:
        run_local(fake, photo_path, monkeypatch)
    assert e.value.code == "no_match"


def test_local_cpu_limit_message_is_a_timeout_not_no_match(photo_path, monkeypatch):
    fake = FakeSolveField(solved=False, engine_output="Total CPU time limit reached!\nField 1 did not solve")
    with pytest.raises(solver.SolveFailed) as e:
        run_local(fake, photo_path, monkeypatch)
    assert e.value.code == "solve_timeout"


def test_local_wall_clock_timeout(photo_path, monkeypatch):
    import subprocess

    fake = FakeSolveField(engine_raises=subprocess.TimeoutExpired("astrometry-engine", 1))
    with pytest.raises(solver.SolveFailed) as e:
        run_local(fake, photo_path, monkeypatch)
    assert e.value.code == "solve_timeout" and e.value.detected_stars == 30


@pytest.mark.parametrize(
    "fake_kwargs", [{"augment_rc": 1}, {"augment_raises": FileNotFoundError()}, {"engine_rc": 2, "solved": False}]
)
def test_local_crashes_are_reported_as_unavailable_not_as_a_bad_photo(photo_path, monkeypatch, fake_kwargs):
    with pytest.raises(solver.LocalSolverUnavailable):
        run_local(FakeSolveField(**fake_kwargs), photo_path, monkeypatch)


def test_local_leaves_no_temp_files_behind(photo_path, monkeypatch):
    import glob
    import tempfile

    before = set(glob.glob(f"{tempfile.gettempdir()}/solve-*"))
    run_local(FakeSolveField(), photo_path, monkeypatch)
    assert set(glob.glob(f"{tempfile.gettempdir()}/solve-*")) == before


# --- which solver runs (decision table) ---------------------------------------------------


def fake_output(name):
    with fits.open(io.BytesIO(axy_bytes(STARS))) as axy:
        return solver.build_output(name, make_wcs_header(), axy, W, H, 20)


@pytest.fixture
def calls(monkeypatch):
    log = []

    def local_ok(*a, **k):
        log.append("local")
        return fake_output("local")

    def nova_ok(*a, **k):
        log.append("nova")
        return fake_output("nova")

    monkeypatch.setattr(solver, "_solve_local", local_ok)
    monkeypatch.setattr(solver, "_solve_nova", nova_ok)
    monkeypatch.setattr(solver, "local_available", lambda: True)
    monkeypatch.delenv("SOLVER_MODE", raising=False)
    return log


def solve_it(photo_path):
    return solver.solve(photo_path, 43.0, -78.79, None)


def test_auto_prefers_local(photo_path, calls):
    assert solve_it(photo_path)["solver_used"] == "local" and calls == ["local"]


def test_auto_uses_api_when_solve_field_is_not_installed(photo_path, calls, monkeypatch):
    monkeypatch.setattr(solver, "local_available", lambda: False)
    assert solve_it(photo_path)["solver_used"] == "nova" and calls == ["nova"]


def test_auto_uses_api_when_local_crashes(photo_path, calls, monkeypatch):
    def crash(*a, **k):
        calls.append("local")
        raise solver.LocalSolverUnavailable("boom")

    monkeypatch.setattr(solver, "_solve_local", crash)
    assert solve_it(photo_path)["solver_used"] == "nova" and calls == ["local", "nova"]


@pytest.mark.parametrize("failure", [solver.no_match(40), solver.too_few_stars(2), solver.solve_timeout(40)])
def test_auto_does_not_retry_on_the_api_after_a_completed_local_failure(photo_path, calls, monkeypatch, failure):
    def fail(*a, **k):
        calls.append("local")
        raise failure

    monkeypatch.setattr(solver, "_solve_local", fail)
    with pytest.raises(solver.SolveFailed) as e:
        solve_it(photo_path)
    assert e.value.code == failure.code and calls == ["local"]  # nova never called


def test_local_mode_never_touches_the_api(photo_path, calls, monkeypatch):
    monkeypatch.setenv("SOLVER_MODE", "local")

    def crash(*a, **k):
        raise solver.LocalSolverUnavailable("boom")

    monkeypatch.setattr(solver, "_solve_local", crash)
    with pytest.raises(solver.SolveFailed) as e:
        solve_it(photo_path)
    assert e.value.code == "solver_unavailable" and calls == []


def test_auto_without_local_or_key_says_unavailable(photo_path, monkeypatch):
    monkeypatch.delenv("SOLVER_MODE", raising=False)
    monkeypatch.delenv("ASTROMETRY_API_KEY", raising=False)
    monkeypatch.setattr(solver, "local_available", lambda: False)
    with pytest.raises(solver.SolveFailed) as e:
        solve_it(photo_path)
    assert e.value.code == "solver_unavailable"


# --- trying several field-size windows when there is no camera data -----------------------


def test_with_exif_there_is_one_window_around_the_focal_length():
    assert solver.scale_stages_deg(1600, 1200, 26) == [solver.scale_range_deg(1600, 1200, 26)]


@pytest.mark.parametrize("missing", [None, 0])
def test_without_exif_phone_windows_are_tried_most_likely_first(missing):
    stages = solver.scale_stages_deg(1440, 1920, missing)
    assert stages[0] == (30.0, 80.0)  # phone main camera, portrait or landscape
    assert set(stages) == {(30.0, 80.0), (10.0, 30.0), (80.0, 120.0)}


def test_the_windows_cover_real_phone_fields_between_telephoto_and_ultra_wide():
    covered = lambda deg: any(lo <= deg <= hi for lo, hi in solver.NO_EXIF_STAGES)
    for width_deg in (18, 26, 45, 50, 55, 69, 72, 85, 108):  # tele, main (portrait/landscape), ultra-wide
        assert covered(width_deg), width_deg


def test_stage_budgets_add_up_to_the_limit_and_favour_the_first():
    one = solver.stage_budgets(1, 90)
    three = solver.stage_budgets(3, 90)
    assert one == [90]
    assert sum(three) == pytest.approx(90) and three[0] > three[1] == three[2]


def test_a_later_window_can_solve_without_extracting_stars_again(photo_path, monkeypatch):
    stages = [(30.0, 80.0), (10.0, 30.0), (80.0, 120.0)]
    fake = FakeSolveField(solve_on_call=2)  # the first window finds nothing, the second solves
    out = run_local(fake, photo_path, monkeypatch, scales=stages)
    assert out.stars_matched == 21
    assert fake.engine_calls == 2
    assert [c[0] for c in fake.commands].count("solve-field") == 1  # stars extracted once
    (lo1, hi1, _), (lo2, hi2, _) = fake.engine_windows
    assert (lo1, hi1) == pytest.approx((30, 80)) and (lo2, hi2) == pytest.approx((10, 30))


def test_each_window_gets_its_own_time_budget(photo_path, monkeypatch):
    monkeypatch.setenv("LOCAL_SOLVE_TIMEOUT_S", "100")
    stages = [(30.0, 80.0), (10.0, 30.0), (80.0, 120.0)]
    fake = FakeSolveField(solved=False)
    with pytest.raises(solver.SolveFailed):
        run_local(fake, photo_path, monkeypatch, scales=stages)
    limits = [c for _, _, c in fake.engine_windows]
    assert limits == [55, 22, 22]  # 55% then the rest split; ANCLIM is a whole number of seconds
    assert sum(limits) <= 100


def test_a_window_that_times_out_does_not_stop_the_next_one(photo_path, monkeypatch):
    fake = FakeSolveField(solve_on_call=2, timeout_calls=(1,))
    out = run_local(fake, photo_path, monkeypatch, scales=[(30.0, 80.0), (10.0, 30.0)])
    assert out.solver_used == "local" and fake.engine_calls == 2


def test_all_windows_searched_with_no_match_is_no_match(photo_path, monkeypatch):
    fake = FakeSolveField(solved=False, engine_output="Field 1 did not solve")
    with pytest.raises(solver.SolveFailed) as e:
        run_local(fake, photo_path, monkeypatch, scales=list(solver.NO_EXIF_STAGES))
    assert e.value.code == "no_match" and fake.engine_calls == 3


def test_any_window_running_out_of_time_makes_the_failure_a_timeout(photo_path, monkeypatch):
    fake = FakeSolveField(solved=False, engine_output="Field 1 did not solve", timeout_calls=(2,))
    with pytest.raises(solver.SolveFailed) as e:
        run_local(fake, photo_path, monkeypatch, scales=list(solver.NO_EXIF_STAGES))
    assert e.value.code == "solve_timeout" and fake.engine_calls == 3


def test_solve_passes_the_windows_to_the_local_solver(photo_path, monkeypatch):
    seen = {}

    def fake_local(path, w, h, scales, step):
        seen["scales"] = scales
        return fake_output("local")

    monkeypatch.setenv("SOLVER_MODE", "local")
    monkeypatch.setattr(solver, "_solve_local", fake_local)
    solver.solve(photo_path, 43.0, -78.79, None)  # no hints: no camera data
    assert seen["scales"] == solver.NO_EXIF_STAGES
    solver.solve(photo_path, 43.0, -78.79, None, hints={"focal_35mm": 26})
    assert seen["scales"] == [solver.scale_range_deg(W, H, 26)]
