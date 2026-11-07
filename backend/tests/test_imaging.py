import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from app import imaging
from app.errors import ApiError
from tests.conftest import make_photo


def test_read_exif_camera_settings_and_time():
    exif = imaging.read_exif(make_photo())
    assert exif["taken_local"] == datetime(2026, 11, 7, 21, 30, 5)
    assert exif["offset_min"] == -300
    assert exif["exposure_s"] == pytest.approx(1 / 3)
    assert exif["iso"] == 800
    assert exif["f_number"] == pytest.approx(1.8)
    assert exif["make_model"] == "Google Pixel 9"


def test_read_exif_on_photo_without_exif_never_raises():
    exif = imaging.read_exif(make_photo(taken=None, offset=None, exposure=None, iso=None, f_number=None, gps=False))
    assert exif["taken_local"] is None and exif["iso"] is None
    assert imaging.read_exif(b"not an image at all")["taken_local"] is None


def test_taken_at_exif_with_offset():
    exif = imaging.read_exif(make_photo())  # 21:30 at -05:00
    dt, source = imaging.resolve_taken_at(exif, None, None)
    assert dt == datetime(2026, 11, 8, 2, 30, 5, tzinfo=timezone.utc)
    assert source == "exif+exif_offset"


def test_taken_at_exif_without_offset_uses_client_offset():
    exif = imaging.read_exif(make_photo(offset=None))
    dt, source = imaging.resolve_taken_at(exif, None, -300)
    assert dt == datetime(2026, 11, 8, 2, 30, 5, tzinfo=timezone.utc)
    assert source == "exif+client_offset"


def test_taken_at_client_fallback_when_no_exif_time():
    exif = imaging.read_exif(make_photo(taken=None, offset=None))
    dt, source = imaging.resolve_taken_at(exif, "2026-11-07T21:30:05-05:00", None)
    assert dt == datetime(2026, 11, 8, 2, 30, 5, tzinfo=timezone.utc)
    assert source == "client"
    dt, _ = imaging.resolve_taken_at(exif, "2026-11-08T02:30:05Z", None)
    assert dt == datetime(2026, 11, 8, 2, 30, 5, tzinfo=timezone.utc)


def test_taken_at_missing_everywhere_is_a_plain_error():
    exif = imaging.read_exif(make_photo(taken=None, offset=None))
    with pytest.raises(ApiError) as e:
        imaging.resolve_taken_at(exif, None, None)
    assert e.value.code == "no_capture_time" and e.value.next_step
    with pytest.raises(ApiError):
        imaging.resolve_taken_at(exif, "garbage", None)


def test_exif_time_without_any_offset_falls_back_to_client_taken_at():
    exif = imaging.read_exif(make_photo(offset=None))
    dt, source = imaging.resolve_taken_at(exif, "2026-11-08T02:30:05Z", None)
    assert source == "client" and dt.hour == 2


def test_strip_removes_all_exif_including_gps():
    raw = make_photo()
    assert 0x8825 in Image.open(io.BytesIO(raw)).getexif()  # the input really has GPS
    clean, w, h = imaging.strip_and_resize(raw)
    out = Image.open(io.BytesIO(clean))
    assert len(out.getexif()) == 0
    assert not out.getexif().get_ifd(0x8825)
    assert "exif" not in out.info and "icc_profile" not in out.info
    assert (w, h) == out.size == (400, 300)


def test_strip_downsizes_large_but_never_upscales():
    big, w, h = imaging.strip_and_resize(make_photo(size=(4000, 3000)))
    assert (w, h) == (2048, 1536)
    _, w, h = imaging.strip_and_resize(make_photo(size=(300, 200)))
    assert (w, h) == (300, 200)


def test_strip_bakes_in_orientation():
    clean, w, h = imaging.strip_and_resize(make_photo(size=(400, 300), orientation=6))  # rotate 90
    assert (w, h) == (300, 400)
    assert len(Image.open(io.BytesIO(clean)).getexif()) == 0


def test_png_is_accepted():
    clean, w, h = imaging.strip_and_resize(make_photo(fmt="PNG"))
    assert Image.open(io.BytesIO(clean)).format == "JPEG"


def test_sniff_rejects_heic_and_garbage():
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 50
    with pytest.raises(ApiError) as e:
        imaging.sniff_format(heic)
    assert e.value.code == "heic_unsupported"
    with pytest.raises(ApiError) as e:
        imaging.sniff_format(b"just some text pretending to be a photo")
    assert e.value.code == "not_an_image"


def test_corrupt_jpeg_is_a_plain_error():
    with pytest.raises(ApiError) as e:
        imaging.strip_and_resize(b"\xff\xd8\xff" + b"\x00" * 100)
    assert e.value.code == "not_an_image"


def test_location_rounded_to_two_decimals_and_validated():
    assert imaging.parse_location("43.00083", "-78.78972") == (43.0, -78.79)
    for lat, lon in [("91", "0"), ("0", "181"), ("abc", "0"), ("nan", "0"), (None, None), ("inf", "0")]:
        with pytest.raises(ApiError) as e:
            imaging.parse_location(lat, lon)
        assert e.value.code == "bad_location"
