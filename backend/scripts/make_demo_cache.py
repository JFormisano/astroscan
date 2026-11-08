"""Generate PLACEHOLDER demo results into backend/demo_cache/. Owner: Person D (#11).

Run from backend/:   python scripts/make_demo_cache.py

These are hand-made stand-ins so demo mode works before real solves do. They follow the
same job shape as GET /api/measurements/{job_id} and Person C's proposed result shape
(frontend/src/fake/fakeResult.js) until docs/result-schema.json is agreed.

Both samples show the same patch of sky (Orion) so the only difference is light pollution:
same stars, fewer of them detected downtown. Orion's bright stars use real names and
magnitudes; the faint field stars are random filler.

REPLACE these with real pre-solved photos once matching + scoring work (~hour 14, B helps D):
run a real photo through the pipeline, save its GET /api/measurements/{job_id} response
as demo_cache/<name>.json, and set job_id to "demo-<name>" and is_demo to true.
"""
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `app` imports from backend/
from app.explainer import explain_result  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "demo_cache"
W, H = 1600, 1200

# Orion, positioned in image pixels (origin top-left, x right, y down). Real magnitudes.
ORION = [
    ("betelgeuse", "Betelgeuse", 640, 330, 0.5),
    ("bellatrix", "Bellatrix", 930, 370, 1.6),
    ("mintaka", "Mintaka", 860, 600, 2.2),
    ("alnilam", "Alnilam", 800, 630, 1.7),
    ("alnitak", "Alnitak", 740, 665, 1.8),
    ("saiph", "Saiph", 690, 930, 2.1),
    ("rigel", "Rigel", 990, 900, 0.1),
    ("meissa", "Meissa", 790, 230, 3.4),
]
ORION_LINES = [
    ("betelgeuse", "bellatrix"), ("betelgeuse", "alnitak"), ("bellatrix", "mintaka"),
    ("mintaka", "alnilam"), ("alnilam", "alnitak"), ("alnitak", "saiph"),
    ("mintaka", "rigel"), ("betelgeuse", "meissa"), ("bellatrix", "meissa"),
]

SAMPLES = {
    "buffalo-downtown": {
        "seed": 11,
        "limiting_mag": 4.3,  # bright city sky: only the brighter stars survive
        "score": 7,
        "confidence": "medium",
        "lat": 42.89, "lon": -78.88,
        "taken_at_utc": "2026-11-07T07:30:00Z",
        "flags": {"exposure_s": 3.0, "iso": 1600, "f_number": 1.7, "solve_seconds": 14.2,
                  "solver_used": "local"},
    },
    "dark-site": {
        "seed": 23,
        "limiting_mag": 6.2,  # rural sky: most naked-eye stars detected
        "score": 3,
        "confidence": "medium",
        "lat": 42.73, "lon": -78.47,
        "taken_at_utc": "2026-11-07T08:10:00Z",
        "flags": {"exposure_s": 3.0, "iso": 1600, "f_number": 1.7, "solve_seconds": 11.8,
                  "solver_used": "local"},
    },
}


def detection_probability(mag, limiting_mag):
    """Smooth drop-off: 50% chance of being detected at the limiting magnitude."""
    return 1 / (1 + math.exp((mag - limiting_mag) * 3))


def make_job(name, cfg):
    rand = random.Random(cfg["seed"])
    lim = cfg["limiting_mag"]

    stars = [
        {"id": sid, "name": label, "x": x, "y": y, "mag": mag, "detected": mag < lim}
        for sid, label, x, y, mag in ORION
    ]
    field = random.Random(42)  # same field stars in every sample, so the samples are comparable
    for i in range(260):
        mag = round(3 + field.random() * 4, 1)  # 3.0–7.0
        x, y = round(field.random() * W), round(field.random() * H)
        stars.append({"id": f"hyg-{i}", "name": None, "x": x, "y": y, "mag": mag,
                      "detected": rand.random() < detection_probability(mag, lim)})

    detected = [s for s in stars if s["detected"]]
    sources = [{"x": round(s["x"] + (rand.random() - 0.5) * 4, 1),
                "y": round(s["y"] + (rand.random() - 0.5) * 4, 1)} for s in detected]
    sources += [{"x": round(rand.random() * W, 1), "y": round(rand.random() * H, 1)}
                for _ in range(12)]  # noise / hot pixels the solver also picks up

    naked_eye = [s for s in stars if s["mag"] < 6]
    pct_lost = round(100 * (1 - sum(s["detected"] for s in naked_eye) / len(naked_eye)))

    pos = {sid: (x, y) for sid, _, x, y, _ in ORION}
    lines = [[*pos[a], *pos[b]] for a, b in ORION_LINES]

    result = {
        "image": {"url": None, "width": W, "height": H},  # no photo yet: overlay draws a dark sky
        "taken_at_utc": cfg["taken_at_utc"],
        "location": {"lat": cfg["lat"], "lon": cfg["lon"]},
        "score": {"value": cfg["score"], "limiting_mag": lim, "pct_lost": pct_lost,
                  "confidence": cfg["confidence"]},
        "stars": stars,
        "constellations": [{"name": "Orion", "label": {"x": 1010, "y": 520}, "lines": lines}],
        "planets": [],
        "warnings": [],
        "sources": sources,
        "stats": {
            "stars_detected": len(sources),
            "stars_matched": len(detected),
            "catalog_in_frame": len(stars),
            "field_width_deg": 38.2,
            "field_height_deg": 28.9,
            "solve_seconds": cfg["flags"]["solve_seconds"],
            "solver_used": cfg["flags"]["solver_used"],
        },
        "explainer": None,  # filled in below from the free template
    }

    # Cached explainer text from the same template real results use (app/explainer.py).
    # Demo mode never calls the Claude API.
    result["explainer"] = explain_result(result)

    # Same top-level shape as GET /api/measurements/{job_id}, plus is_demo.
    return {
        "job_id": f"demo-{name}",
        "status": "solved",
        "step": None,
        "result": result,
        "error": None,
        "image_url": None,
        "taken_at_utc": cfg["taken_at_utc"],
        "lat": cfg["lat"],
        "lon": cfg["lon"],
        "flags": cfg["flags"],
        "is_demo": True,
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for name, cfg in SAMPLES.items():
        path = OUT_DIR / f"{name}.json"
        path.write_text(json.dumps(make_job(name, cfg), indent=1) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(OUT_DIR.parent)}")


if __name__ == "__main__":
    main()
