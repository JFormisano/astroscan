"""AI explainer (#10): the free template explains a scored result; Claude is optional."""
import json
import re

import pytest

from app import ai, explainer
from app.routes import demo


def scored(value=7, limiting=4.3, pct=58, confidence="medium", **extra):
    return {"score": {"value": value, "limiting_mag": limiting, "pct_lost": pct, "confidence": confidence},
            "constellations": [{"name": "Orion"}], "planets": [{"name": "Jupiter"}], **extra}


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_explains_the_numbers_it_was_given():
    text = explainer.explain_result(scored())
    assert "scored 7 out of 9" in text
    assert "a suburban / city edge sky" in text  # same name as the score card
    assert "magnitude 4.3" in text
    assert "About 58%" in text
    assert "Orion and Jupiter" in text
    assert "as your phone saw it" in text
    assert text.count("\n\n") == 2  # three short paragraphs


@pytest.mark.parametrize("value,phrase", [(2, "rare and worth protecting"),
                                          (5, "bring back many of the hidden stars"),
                                          (8, "report it")])
def test_what_helps_fits_the_sky(value, phrase):
    assert phrase in explainer.explain_result(scored(value=value))


def test_never_invents_numbers():
    """Every number in the text came from the input (or is the fixed 1/9 scale or 3000 K)."""
    text = explainer.explain_result(scored(value=6, limiting=5.1, pct=37))
    numbers = set(re.findall(r"\d+(?:\.\d+)?", text))
    assert numbers <= {"6", "9", "1", "5.1", "37", "3000"}


def test_no_score_means_no_explainer():
    assert explainer.explain_result(None) is None
    assert explainer.explain_result({}) is None
    assert explainer.explain_result({"solver_used": "local", "wcs": {}}) is None  # raw solver block today
    assert explainer.explain_result({"score": {"value": 12}}) is None


def test_missing_pieces_are_skipped_not_guessed():
    text = explainer.explain_result({"score": {"value": 4}})
    assert "scored 4 out of 9" in text
    assert "magnitude" not in text and "%" not in text and "pick out" not in text


def test_warnings_lower_trust():
    text = explainer.explain_result(scored(confidence="low", warnings=[
        {"type": "twilight"}, {"type": "moon", "moon_illumination_pct": 42.4}, {"type": "low_altitude"}]))
    assert "wasn't fully dark" in text
    assert "Moon was up (42% lit)" in text
    assert "close to the horizon" in text
    assert "rough guess" in text


def test_reads_person_b_conditions_flags_too():
    text = explainer.explain_result(scored(conditions={
        "flags": {"twilight": False, "moon_up": True, "low_altitude": False}, "moon_illumination_pct": 80}))
    assert "Moon was up (80% lit)" in text
    assert "wasn't fully dark" not in text


def test_ai_wrapper_uses_template_without_a_key():
    text, source = ai.explain_result(scored())
    assert source == "template"
    assert text == explainer.explain_result(scored())
    assert ai.explain_result({}) == (None, "template")


def test_ai_wrapper_falls_back_when_claude_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "_ask_claude", lambda system, user: None)
    assert ai.explain_result(scored()) == (explainer.explain_result(scored()), "template")


def test_ai_wrapper_sends_only_computed_facts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sent = {}

    def fake_claude(system, user):
        sent.update(json.loads(user))
        return "Claude's explanation"

    monkeypatch.setattr(ai, "_ask_claude", fake_claude)
    assert ai.explain_result(scored()) == ("Claude's explanation", "ai")
    assert sent["score"] == 7 and sent["visible"] == ["Orion", "Jupiter"]


@pytest.mark.parametrize("path", sorted(demo.DEMO_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_demo_explainers_come_from_the_template(path):
    """Regenerate with scripts/make_demo_cache.py if this fails after a template change."""
    result = json.loads(path.read_text(encoding="utf-8"))["result"]
    assert result["explainer"] == explainer.explain_result(result)
