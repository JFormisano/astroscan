"""Routes for demo. Owner: Person D (#11). See the API table in CLAUDE.md section 3.

GET /api/demo/{name} returns a pre-solved result from demo_cache/{name}.json, in the same
shape as GET /api/measurements/{job_id}, so the results page draws it with no changes.

Demo mode must always work (CLAUDE.md section 5): it reads local files only and never calls
the solver, the database or the Claude API.
"""
import json
import re
from pathlib import Path

from fastapi import APIRouter

from app.errors import ApiError

router = APIRouter()

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "demo_cache"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")  # also blocks paths like ../../.env


def _not_found() -> ApiError:
    return ApiError(
        404,
        "demo_not_found",
        "We couldn't find that sample photo.",
        "Go back to the home page and tap \"Try a sample photo\".",
    )


@router.get("/demo/{name}")
def get_demo(name: str):
    if not NAME_RE.match(name):
        raise _not_found()
    path = DEMO_DIR / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _not_found() from None
