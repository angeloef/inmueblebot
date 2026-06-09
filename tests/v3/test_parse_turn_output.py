"""V3 engine output parsing — tolerance for noisy LLM responses.

Regression for the clarify-loop bug: the engine model (gpt-5.4-mini) sometimes
appends trailing text on a second line despite strict structured outputs, e.g.

    {"belief_delta": {...}, ...}
    Aquí tienes la respuesta.

A plain ``json.loads`` raises "Extra data: line 2 column 1", the whole turn is
discarded, and the caller falls back to a confidence=0.0 regex clarify — re-asking
what the user already answered ("¿alquilar o comprar?" after they said "comprar").

These tests lock in that ``parse_turn_output`` decodes only the first JSON object
and tolerates surrounding noise.

Offline: no DB / Redis / LLM.
"""

from __future__ import annotations

import json

import pytest

from app.routers.v3.schema import parse_turn_output


def _valid_payload() -> dict:
    return {
        "belief_delta": {
            "operation": "venta",
            "property_type": "casa",
            "zone": "Oberá",
            "budget_max": 200000,
            "bedrooms_min": None,
        },
        "intent": "search",
        "action": "search",
        "tool_calls": [],
        "selected_property_id": None,
        "missing_slot": None,
        "response_plan": [{"type": "text", "content": "Buscando..."}],
        "confidence": 0.95,
    }


def test_parses_clean_json():
    turn = parse_turn_output(json.dumps(_valid_payload()))
    assert turn.action == "search"
    assert turn.belief_delta.operation == "venta"
    assert turn.belief_delta.property_type == "casa"


def test_tolerates_trailing_text_on_second_line():
    """The actual production failure: object + trailing prose on line 2."""
    raw = json.dumps(_valid_payload()) + "\nAquí tienes las opciones disponibles."
    turn = parse_turn_output(raw)
    assert turn.action == "search"
    assert turn.belief_delta.budget_max == 200000


def test_tolerates_markdown_code_fences():
    raw = "```json\n" + json.dumps(_valid_payload()) + "\n```"
    turn = parse_turn_output(raw)
    assert turn.action == "search"
    assert turn.belief_delta.zone == "Oberá"


def test_tolerates_leading_prose_before_object():
    raw = "Here is the result:\n" + json.dumps(_valid_payload())
    turn = parse_turn_output(raw)
    assert turn.action == "search"


def test_raises_when_no_json_object_present():
    with pytest.raises(ValueError):
        parse_turn_output("no json here at all")
