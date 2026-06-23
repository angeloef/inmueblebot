"""Offline tests for V4 KA1 perception layer.

Tests cover schema parsing and sub_goals/references extraction.
No LLM, no DB, no Redis required.
"""

from __future__ import annotations

import json

import pytest


# ── Helper: build a valid V4 JSON string ─────────────────────────────────────

def _v4_json(sub_goals: list[dict], references: dict | None = None, **overrides) -> str:
    base = {
        "belief_delta": {
            "operation": None, "property_type": None, "zone": None,
            "budget_max": None, "bedrooms_min": None, "bedrooms_max": None, "bedrooms_match": None,
        },
        "intent": "rapport",
        "action": "smalltalk",
        "tool_calls": [],
        "selected_property_id": None,
        "missing_slot": None,
        "response_plan": [{"type": "text", "content": "Hola, ¿en qué te ayudo?"}],
        "confidence": 0.9,
        "sub_goals": sub_goals,
        "references": references or {"selected_property_id": None, "anaphora": None},
    }
    base.update(overrides)
    return json.dumps(base)


# ── Schema tests ──────────────────────────────────────────────────────────────

def test_turn_json_schema_v4_has_sub_goals_and_references():
    from app.routers.v4.schema import TURN_JSON_SCHEMA_V4
    props = TURN_JSON_SCHEMA_V4["schema"]["properties"]
    assert "sub_goals" in props
    assert "references" in props


def test_turn_json_schema_v4_required_includes_new_fields():
    from app.routers.v4.schema import TURN_JSON_SCHEMA_V4
    required = set(TURN_JSON_SCHEMA_V4["schema"]["required"])
    assert "sub_goals" in required
    assert "references" in required


def test_turn_json_schema_v4_strict_mode():
    from app.routers.v4.schema import TURN_JSON_SCHEMA_V4
    assert TURN_JSON_SCHEMA_V4.get("strict") is True
    assert TURN_JSON_SCHEMA_V4["schema"].get("additionalProperties") is False


# ── Parser tests ──────────────────────────────────────────────────────────────

def test_parse_turn_output_v4_single_intent():
    from app.routers.v4.schema import parse_turn_output_v4

    raw = _v4_json([{"intent": "rapport", "args_hint": "{}"}])
    result = parse_turn_output_v4(raw)

    assert len(result.sub_goals) == 1
    assert result.sub_goals[0].intent == "rapport"
    assert result.sub_goals[0].parsed_args() == {}


def test_parse_turn_output_v4_multi_intent():
    from app.routers.v4.schema import parse_turn_output_v4

    raw = _v4_json(
        sub_goals=[
            {"intent": "search", "args_hint": '{"operation":"alquiler","tipo":"departamento"}'},
            {"intent": "scheduling", "args_hint": '{"dia":"sabado"}'},
        ],
        intent="search",
        action="search",
    )
    result = parse_turn_output_v4(raw)

    assert len(result.sub_goals) == 2
    assert result.sub_goals[0].intent == "search"
    assert result.sub_goals[0].parsed_args()["operation"] == "alquiler"
    assert result.sub_goals[1].intent == "scheduling"
    assert result.sub_goals[1].parsed_args()["dia"] == "sabado"


def test_parse_turn_output_v4_anaphora_references():
    from app.routers.v4.schema import parse_turn_output_v4

    raw = _v4_json(
        sub_goals=[{"intent": "knowledge", "args_hint": '{"topic":"precio"}'}],
        references={"selected_property_id": 42, "anaphora": "ese"},
        intent="knowledge",
        action="answer_knowledge",
    )
    result = parse_turn_output_v4(raw)

    assert result.references.selected_property_id == 42
    assert result.references.anaphora == "ese"


def test_parse_turn_output_v4_robust_trailing_text():
    """raw_decode must ignore trailing text after the JSON object."""
    from app.routers.v4.schema import parse_turn_output_v4

    raw = _v4_json([{"intent": "rapport", "args_hint": "{}"}])
    raw_with_trailing = raw + "\nExtra trailing text the model appended."
    result = parse_turn_output_v4(raw_with_trailing)

    assert len(result.sub_goals) == 1


def test_parse_turn_output_v4_preserves_v3_fields():
    """All V3 fields must still be present and accessible."""
    from app.routers.v4.schema import parse_turn_output_v4

    raw = _v4_json(
        sub_goals=[{"intent": "search", "args_hint": '{"operation":"alquiler"}'}],
        intent="search",
        action="search",
        belief_delta={
            "operation": "alquiler", "property_type": "departamento", "zone": None,
            "budget_max": None, "bedrooms_min": None, "bedrooms_max": None, "bedrooms_match": None,
        },
    )
    result = parse_turn_output_v4(raw)

    assert result.intent == "search"
    assert result.action == "search"
    assert result.belief_delta.operation == "alquiler"
    assert result.belief_delta.property_type == "departamento"
    assert result.confidence == 0.9


# ── SubGoal model test ────────────────────────────────────────────────────────

def test_sub_goal_parsed_args_invalid_json():
    from app.routers.v4.schema import SubGoal

    sg = SubGoal(intent="search", args_hint="not-valid-json{{{")
    assert sg.parsed_args() == {}


def test_sub_goal_parsed_args_empty():
    from app.routers.v4.schema import SubGoal

    sg = SubGoal(intent="rapport", args_hint="{}")
    assert sg.parsed_args() == {}
