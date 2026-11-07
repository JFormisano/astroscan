import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app import solver
from app.db import LocalStore, get_store
from app.main import app


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path)


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("SOLVER_MODE", "stub")
    monkeypatch.setattr(solver, "STUB_DELAY_S", 0)
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_photo(
    *,
    size=(400, 300),
    taken="2026:11:07 21:30:05",
    offset="-05:00",
    exposure=(1, 3),
    iso=800,
    f_number=(18, 10),
    gps=True,
    orientation=None,
    fmt="JPEG",
) -> bytes:
    """Build a small test photo with EXIF (incl. GPS by default, to prove it gets stripped)."""
    img = Image.new("RGB", size, (5, 5, 20))
    img.putpixel((10, 10), (255, 255, 255))
    exif = Image.Exif()
    exif[0x010F] = "Google"
    exif[0x0110] = "Pixel 9"
    if orientation:
        exif[0x0112] = orientation
    ifd = {}
    if taken:
        ifd[0x9003] = taken
    if offset:
        ifd[0x9011] = offset
    if exposure:
        ifd[0x829A] = IFDRational(*exposure)
    if iso:
        ifd[0x8827] = iso
    if f_number:
        ifd[0x829D] = IFDRational(*f_number)
    if ifd:
        exif[0x8769] = ifd
    if gps:
        exif[0x8825] = {1: "N", 2: (43.0, 0.0, 8.0), 3: "W", 4: (78.0, 47.0, 20.0)}
    buf = io.BytesIO()
    if fmt == "PNG":
        img.save(buf, format="PNG")
    else:
        img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture
def photo():
    return make_photo
