"""Light-report message templates. Owner: Person D (#9).

This is the free, default way drafts are written: no API key, no outside call, instant, and it
never fails. Each light type gets its own problem description and fixes, and each recipient gets
its own greeting and closing. (If ANTHROPIC_API_KEY is ever set, app/ai.py tries Claude first
and falls back to this.)

Keys match the frontend (frontend/src/pages/LightReport.jsx).
"""

# category key -> how people read it, plus what to say about it.
CATEGORIES = {
    "streetlight": {
        "label": "Streetlight",
        "what": "a streetlight",
        "problem": "Its light spreads sideways and upward instead of staying on the street, which "
                   "adds glare for drivers and walkers and brightens the night sky.",
        "fixes": [
            "a fully shielded (full-cutoff) fixture that aims all the light down at the road",
            "a warmer LED (3000 K or below), which causes less glare and sky glow",
            "dimming it late at night when there's little traffic",
        ],
    },
    "floodlight": {
        "label": "Floodlight or security light",
        "what": "a floodlight",
        "problem": "It's aimed outward, so much of its light goes past the area it's meant to cover "
                   "and into the sky and nearby windows. Glare like this can also make it harder, "
                   "not easier, to see what's in the shadows.",
        "fixes": [
            "aiming it down or adding a shield so it lights only the ground it needs to",
            "a motion sensor, so it comes on only when someone is there",
            "a lower-wattage, warmer bulb (3000 K or below)",
        ],
    },
    "parking": {
        "label": "Parking lot light",
        "what": "a parking lot light",
        "problem": "The lot is lit brightly through the night, including hours when it's nearly "
                   "empty, and the light spills past the lot into the sky and surroundings.",
        "fixes": [
            "fully shielded fixtures that point straight down at the pavement",
            "dimming or switching off part of the lot after closing hours",
            "warmer LEDs (3000 K or below)",
        ],
    },
    "building": {
        "label": "Building or wall light",
        "what": "a light on the outside of a building",
        "problem": "It shines up the wall or outward, so a lot of it ends up in the sky or "
                   "neighbors' windows instead of on the entrance or path it's meant for.",
        "fixes": [
            "a shielded fixture aimed down at the doorway or path",
            "a timer that turns decorative or facade lighting off late at night (for example, after 11 pm)",
            "a warmer, lower-brightness bulb (3000 K or below)",
        ],
    },
    "sign": {
        "label": "Sign or billboard",
        "what": "an illuminated sign",
        "problem": "It stays at full brightness through the night, long after most people pass by, "
                   "and lights up the surrounding area and sky.",
        "fixes": [
            "dimming it after business hours (many digital signs have a night mode)",
            "turning it off after closing",
            "lowering its overall brightness at night",
        ],
    },
    "sports": {
        "label": "Sports field light",
        "what": "sports field lighting",
        "problem": "The lights spill well beyond the field and sometimes stay on after games or "
                   "practice have ended.",
        "fixes": [
            "switching the lights off promptly when the field isn't in use",
            "visors or shields that keep the light on the playing area",
            "a timer or schedule so they can't be left on by accident",
        ],
    },
    "other": {
        "label": "Outdoor light",
        "what": "an outdoor light",
        "problem": "It sends a lot of light into the sky and toward neighbors instead of only "
                   "where it's needed.",
        "fixes": [
            "a fully shielded fixture that points the light down",
            "a warmer bulb (3000 K or below)",
            "a timer or motion sensor so it's off when nobody needs it",
        ],
    },
}

# controller key -> who the message is addressed to, and wording that fits them.
RECIPIENTS = {
    "ub": {
        "name": "UB Facilities",
        "greeting": "Hello UB Facilities,",
        "intro": "I'm part of the UB community and wanted to let you know about {what} on campus.",
        "closing": "Changes like these save energy and would fit well with the university's "
                   "sustainability efforts. They'd also let students see more of the night sky.",
    },
    "municipal": {
        "name": "the town or city public works department",
        "greeting": "Hello Public Works team,",
        "intro": "I'm a local resident writing about {what} in our area.",
        "closing": "Many communities have updated their outdoor lighting this way to cut energy "
                   "costs while keeping streets safe.",
    },
    "business": {
        "name": "the property owner or manager",
        "greeting": "Hello,",
        "intro": "I'm a neighbor writing about {what} at your property.",
        "closing": "Changes like these often pay for themselves through lower electricity bills.",
    },
    "unknown": {
        "name": "whoever manages this light",
        "greeting": "Hello,",
        "intro": "I'm writing about {what} in the area. If you're not the right contact, could you "
                 "please pass this along to whoever manages it?",
        "closing": "Changes like these are usually low-cost and save energy.",
    },
}


def category_label(category: str) -> str:
    return CATEGORIES.get(category, CATEGORIES["other"])["label"]


def recipient_name(controller: str) -> str:
    return RECIPIENTS.get(controller, RECIPIENTS["unknown"])["name"]


def light_report_message(*, category: str, controller: str, note: str | None,
                         lat: float, lon: float, nearby_score: int | None = None) -> str:
    """A complete, polite request. Plain text, ready to copy into an email or web form."""
    cat = CATEGORIES.get(category, CATEGORIES["other"])
    rec = RECIPIENTS.get(controller, RECIPIENTS["unknown"])

    lines = [rec["greeting"], "", rec["intro"].format(what=cat["what"]) + " " + cat["problem"]]
    if note:
        lines += ["", f"What I noticed: {note.strip()}"]
    # Rounded to ~1 km on purpose; the sender can add the exact address before sending.
    lines += ["", f"Approximate location: {lat:.2f}, {lon:.2f}. I'm happy to share the exact spot."]
    if nearby_score is not None:
        lines += ["", f"A sky reading taken nearby scored {nearby_score} out of 9 on a Bortle-style "
                      "scale (1 is darkest), so light here is already washing out the night sky."]
    lines += ["", "Would you consider any of these low-cost fixes?"]
    lines += [f"- {fix[0].upper()}{fix[1:]}" for fix in cat["fixes"]]
    lines += ["", rec["closing"], "", "Thank you for considering it.", "", "A neighbor"]
    return "\n".join(lines)
