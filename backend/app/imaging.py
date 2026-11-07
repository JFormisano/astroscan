"""Upload image handling: validate, read EXIF, strip EXIF, resize, round coordinates.

Owner: Person A. Pure functions (no I/O beyond the bytes passed in) so they are easy to test.

Order matters for privacy: read what we need from EXIF FIRST (`read_exif`), then build the
stripped copy (`strip_and_resize`). Only the stripped copy is ever stored or sent anywhere.
"""
import io
import math
import warnings
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageOps

from app.errors import ApiError

MAX_LONG_SIDE_PX = 2048  # every later stage (solver, overlays) uses this one stripped copy
JPEG_QUALITY = 92
COORD_DECIMALS = 2  # 0.01 degree is about 1.1 km

# Refuse absurd pixel counts before decoding (decompression bombs).
Image.MAX_IMAGE_PIXELS = 100_000_000

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}

# EXIF tag ids
_EXIF_IFD = 0x8769
_TAG_MAKE, _TAG_MODEL = 0x010F, 0x0110
_TAG_EXPOSURE_TIME = 0x829A
_TAG_F_NUMBER = 0x829D
_TAG_ISO = 0x8827
_TAG_ISO_SPEED = 0x8833
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_OFFSET_TIME_ORIGINAL = 0x9011
_TAG_FOCAL_LENGTH = 0x920A
_TAG_FOCAL_LENGTH_35 = 0xA405


def sniff_format(data: bytes) -> str:
    """Return 'jpeg' or 'png'; raise ApiError for HEIC and anything else.

    Checks the file's magic bytes, never the client's Content-Type or file extension.
    """
    if data.startswith(_JPEG_MAGIC):
        return "jpeg"
    if data.startswith(_PNG_MAGIC):
        return "png"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        raise ApiError(
            415,
            "heic_unsupported",
            "This looks like a HEIC photo, which we can't read yet.",
            "Share or export the photo as JPEG, or set your camera to 'Most Compatible', then upload it again.",
        )
    raise ApiError(
        415,
        "not_an_image",
        "That file isn't a JPEG or PNG photo.",
        "Choose a JPEG or PNG night-sky photo and try again.",
    )


def _open(data: bytes) -> Image.Image:
    sniff_format(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            img.load()
        return img
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ApiError(
            413,
            "image_too_large",
            "That photo has too many pixels for us to process.",
            "Resize it to under 50 megapixels and upload it again.",
        ) from None
    except Exception:  # truncated/corrupt files raise many different errors
        raise ApiError(
            422,
            "not_an_image",
            "We couldn't open that photo — it may be damaged.",
            "Try a different photo, or re-save this one as a JPEG.",
        ) from None


# --- EXIF ---------------------------------------------------------------------------------


def _num(value) -> float | None:
    """EXIF rationals/tuples -> float, or None."""
    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
    try:
        f = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _parse_exif_offset(text) -> int | None:
    """'+05:30' / '-04:00' -> minutes east of UTC."""
    if not isinstance(text, str):
        return None
    text = text.strip().replace("\x00", "")
    if len(text) != 6 or text[0] not in "+-" or text[3] != ":":
        return None
    try:
        minutes = int(text[1:3]) * 60 + int(text[4:6])
    except ValueError:
        return None
    return minutes if text[0] == "+" else -minutes


def _parse_exif_datetime(text) -> datetime | None:
    """'2026:11:07 21:30:05' -> naive datetime (local time of the device), or None."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text.strip().replace("\x00", ""), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def read_exif(data: bytes) -> dict:
    """Pull out only what we need. Never raises: a missing/garbled EXIF block gives None fields.

    Returns: taken_local (naive datetime|None), offset_min (int|None, minutes east of UTC),
    exposure_s, iso, f_number, focal_length_mm, focal_35mm, make_model.
    """
    out = {
        "taken_local": None,
        "offset_min": None,
        "exposure_s": None,
        "iso": None,
        "f_number": None,
        "focal_length_mm": None,
        "focal_35mm": None,
        "make_model": None,
    }
    try:
        with Image.open(io.BytesIO(data)) as img:
            exif = img.getexif()
            ifd = exif.get_ifd(_EXIF_IFD) if exif else {}
    except Exception:
        return out

    out["taken_local"] = _parse_exif_datetime(ifd.get(_TAG_DATETIME_ORIGINAL))
    out["offset_min"] = _parse_exif_offset(ifd.get(_TAG_OFFSET_TIME_ORIGINAL))
    out["exposure_s"] = _num(ifd.get(_TAG_EXPOSURE_TIME))
    out["f_number"] = _num(ifd.get(_TAG_F_NUMBER))
    iso = _num(ifd.get(_TAG_ISO)) or _num(ifd.get(_TAG_ISO_SPEED))
    out["iso"] = int(iso) if iso else None
    out["focal_length_mm"] = _num(ifd.get(_TAG_FOCAL_LENGTH))
    out["focal_35mm"] = _num(ifd.get(_TAG_FOCAL_LENGTH_35))
    make = str(exif.get(_TAG_MAKE) or "").strip().replace("\x00", "") if exif else ""
    model = str(exif.get(_TAG_MODEL) or "").strip().replace("\x00", "") if exif else ""
    if model.lower().startswith(make.lower()):
        make = ""  # "Apple" + "Apple iPhone 15" -> just the model
    out["make_model"] = f"{make} {model}".strip() or None
    return out


# --- capture time -------------------------------------------------------------------------


def _parse_client_taken_at(text: str | None, tz_offset_min: int | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        # A naive client time is local to the device if we know its offset, else assume UTC.
        dt = dt.replace(tzinfo=timezone(timedelta(minutes=tz_offset_min or 0)))
    return dt.astimezone(timezone.utc)


def resolve_taken_at(
    exif: dict, client_taken_at: str | None, client_tz_offset_min: int | None
) -> tuple[datetime, str]:
    """Capture time in UTC plus where it came from. EXIF wins; the client is the fallback.

    Order: EXIF time + EXIF offset -> EXIF time + client offset -> client taken_at -> error.
    `client_tz_offset_min` is minutes EAST of UTC (US Eastern in winter = -300). In JavaScript
    that is `-new Date().getTimezoneOffset()`.
    """
    local = exif.get("taken_local")
    if local is not None:
        if exif.get("offset_min") is not None:
            tz = timezone(timedelta(minutes=exif["offset_min"]))
            return local.replace(tzinfo=tz).astimezone(timezone.utc), "exif+exif_offset"
        if client_tz_offset_min is not None:
            tz = timezone(timedelta(minutes=client_tz_offset_min))
            return local.replace(tzinfo=tz).astimezone(timezone.utc), "exif+client_offset"
    client = _parse_client_taken_at(client_taken_at, client_tz_offset_min)
    if client is not None:
        return client, "client"
    raise ApiError(
        422,
        "no_capture_time",
        "We couldn't tell when this photo was taken.",
        "Enter the date and time you took the photo, then upload again.",
    )


# --- location -----------------------------------------------------------------------------


def parse_location(lat: str | None, lon: str | None) -> tuple[float, float]:
    """Validate raw coordinates and return them rounded to ~1 km. Raw values go no further."""
    try:
        lat_f, lon_f = float(lat), float(lon)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        lat_f = lon_f = math.nan
    if not (math.isfinite(lat_f) and math.isfinite(lon_f) and -90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise ApiError(
            422,
            "bad_location",
            "We couldn't use that location.",
            "Allow location access or pick the spot where you took the photo, then try again.",
        )
    return round(lat_f, COORD_DECIMALS), round(lon_f, COORD_DECIMALS)


# --- stripping ----------------------------------------------------------------------------


def strip_and_resize(data: bytes) -> tuple[bytes, int, int]:
    """Return (jpeg_bytes, width, height) of a metadata-free copy, long side <= 2048 px.

    EXIF orientation is applied to the pixels first, so the image looks right with no tag.
    The pixels are copied into a brand-new image so no EXIF, GPS, ICC or comment data can
    ride along. Never upscales.
    """
    img = _open(data)
    img = ImageOps.exif_transpose(img)  # bake orientation into the pixels
    img = img.convert("RGB")
    img.thumbnail((MAX_LONG_SIDE_PX, MAX_LONG_SIDE_PX), Image.Resampling.LANCZOS)

    clean = Image.new("RGB", img.size)
    clean.paste(img)
    buf = io.BytesIO()
    clean.save(buf, format="JPEG", quality=JPEG_QUALITY)  # no exif=/icc_profile= -> none written
    return buf.getvalue(), clean.width, clean.height
