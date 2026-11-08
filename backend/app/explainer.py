"""Results explainer, free template version (#10). Owner: Person D.

Turns a scored result into a short plain-English "What this means" paragraph plus what helps.
No API key, no outside call, instant, never fails. (If ANTHROPIC_API_KEY is ever set, app/ai.py
tries Claude first and falls back to this.)

It only rephrases numbers the backend already computed (score, limiting magnitude, % lost,
confidence, warnings). It never calculates anything new (CLAUDE.md section 4, "AI").

Input: the result dict in the proposed result shape (frontend/src/fake/fakeResult.js until
docs/result-schema.json is agreed). Missing pieces are skipped, never guessed.
"""

# Same names as the score card (frontend/src/components/ScoreCard.jsx).
SCORE_NAMES = {
    1: "a pristine dark sky",
    2: "a truly dark sky",
    3: "a rural sky",
    4: "a rural / suburban edge sky",
    5: "a suburban sky",
    6: "a bright suburban sky",
    7: "a suburban / city edge sky",
    8: "a city sky",
    9: "an inner-city sky",
}

WHAT_HELPS = {
    "dark": "Skies like this are rare and worth protecting. Outdoor lights that are fully shielded "
            "(pointing down), warm-colored (3000 K or below) and switched off when not needed keep "
            "them dark.",
    "middle": "Most of the glow comes from outdoor lights that shine up or sideways. Fully shielded "
              "fixtures that point down, warmer bulbs (3000 K or below), and lights that switch off "
              "or dim when nobody needs them would bring back many of the hidden stars.",
    "bright": "Light here comes from many sources: streetlights, parking lots, signs and buildings. "
              "Fully shielded fixtures that point down, warmer bulbs (3000 K or below), and turning "
              "lights off when nobody needs them all help. If you spot a light that's especially "
              "bad, you can report it and we'll draft a request for you.",
}


def _int_score(score):
    try:
        value = round(float(score["value"]))
    except (TypeError, KeyError, ValueError):
        return None
    return value if 1 <= value <= 9 else None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _warnings(result):
    """Warning list in the proposed shape, or derived from Person B's conditions flags (renaming only)."""
    if isinstance(result.get("warnings"), list):
        return result["warnings"]
    cond = result.get("conditions") or {}
    flags = cond.get("flags") or {}
    out = []
    if flags.get("twilight"):
        out.append({"type": "twilight"})
    if flags.get("moon_up"):
        out.append({"type": "moon", "moon_illumination_pct": cond.get("moon_illumination_pct")})
    if flags.get("low_altitude"):
        out.append({"type": "low_altitude"})
    return out


def _join(names):
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def explain_result(result: dict | None) -> str | None:
    """Plain-English explanation of a scored result, or None if there's no score to explain."""
    if not isinstance(result, dict):
        return None
    score = result.get("score") or {}
    value = _int_score(score)
    if value is None:
        return None

    limiting = _num(score.get("limiting_mag"))
    pct_lost = _num(score.get("pct_lost"))
    confidence = score.get("confidence")

    # 1. What the score means.
    first = [f"Your sky scored {value} out of 9, which is typical of {SCORE_NAMES[value]} "
             "(1 is darkest, 9 is brightest)."]
    if limiting is not None:
        first.append(f"Your phone picked up stars down to about magnitude {limiting:.1f}; "
                     "the higher that number, the fainter the stars you can see.")
    if pct_lost is not None:
        lost = round(pct_lost)
        if lost >= 1:
            first.append(f"About {lost}% of the naked-eye stars a truly dark sky would show here "
                         "are hidden by artificial light. Tap \"Show the stars light pollution is "
                         "hiding\" above to see them.")
        else:
            first.append("Almost none of the naked-eye stars a dark sky would show are hidden here.")
    seen = _join([c.get("name") for c in result.get("constellations") or [] if isinstance(c, dict)]
                 + [p.get("name") for p in result.get("planets") or [] if isinstance(p, dict)])
    if seen:
        first.append(f"You can still pick out {seen}.")

    # 2. How much to trust it.
    second = []
    warn_types = {w.get("type"): w for w in _warnings(result) if isinstance(w, dict)}
    if "twilight" in warn_types:
        second.append("The sky wasn't fully dark yet when you took this, so the score is brighter "
                      "than the true night sky.")
    if "moon" in warn_types:
        pct = _num(warn_types["moon"].get("moon_illumination_pct"))
        moon = f"The Moon was up ({round(pct)}% lit)" if pct is not None else "The Moon was up"
        second.append(f"{moon}, which brightens the whole sky and hides faint stars.")
    if "low_altitude" in warn_types:
        second.append("You were pointing close to the horizon, where haze and city glow are "
                      "strongest; aim higher for a fairer reading.")
    if confidence == "low":
        second.append("We have low confidence in this score, so treat it as a rough guess.")
    second.append("This is your sky as your phone saw it: exposure, lens and Night mode all "
                  "affect how many stars a photo shows.")

    # 3. What helps.
    band = "dark" if value <= 3 else "middle" if value <= 6 else "bright"

    return "\n\n".join([" ".join(first), " ".join(second), WHAT_HELPS[band]])
