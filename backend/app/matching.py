"""Load the star catalog and constellation stick figures. Owner: Person B.

Matching and projection are not in this module yet. Both loaders read the
JSON in backend/data once and then return the cached list.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_stars():
    """Stars with visual magnitude <= 7. The Sun is not included."""
    return _load("stars.json")


@lru_cache(maxsize=1)
def load_constellations():
    """The 88 IAU stick figures, with segment endpoints in J2000 degrees."""
    return _load("constellation_lines.json")


def _load(filename):
    path = _DATA_DIR / filename
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
