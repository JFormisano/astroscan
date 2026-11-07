"""Plate solving. Owner: Person A.

Right now this is a STUB so the upload -> processing -> results flow works end to end.
Feature #2 replaces the body with local `solve-field` (primary) and the nova.astrometry.net
API (fallback). The signature and the SolveFailed contract below stay the same, so nothing
else changes when we swap.
"""
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

STUB_DELAY_S = 2.0  # pretend the solve takes a moment; tests set this to 0


class SolveFailed(Exception):
    """Raised when the photo can't be solved. Becomes the job's `error`."""

    def __init__(self, message: str, next_step: str = "", detected_stars: int | None = None, code: str = "solve_failed"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_step = next_step
        self.detected_stars = detected_stars


def solve(
    image_path: Path,
    lat: float,
    lon: float,
    taken_at: datetime,
    on_step: Callable[[str], None] | None = None,
) -> dict:
    """Solve one stripped photo. `lat`/`lon` are the ~1 km rounded values; `taken_at` is UTC.

    Calls `on_step("...")` as it progresses so the Processing page can show it. Returns the
    result dict (shape: docs/result-schema.json, once agreed) or raises SolveFailed.
    """
    step = on_step or (lambda _s: None)
    step("Finding stars…")
    time.sleep(STUB_DELAY_S / 2)
    step("Matching constellations…")
    time.sleep(STUB_DELAY_S / 2)
    # TODO: replace with the fake result in demo_cache/ once docs/result-schema.json is agreed.
    return {
        "stub": True,
        "note": "Placeholder result from the stub solver. Real solving is feature #2.",
        "solver_used": "stub",
    }
