"""V4 engine output schema — extends V3 with sub_goals and references (KA1).

OpenAI strict-mode rules enforced throughout (same as V3 schema).
V4 adds two fields to the V3 schema:
  - sub_goals[]: ordered list of sub-objectives (multi-intent support)
  - references{}: anaphora + property-id resolution
All V3 fields are preserved so the V3 execution pipeline works unchanged.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

# Re-export V3 primitives used by the execution pipeline
from app.routers.v3.schema import (  # noqa: F401
    _TOOL_NAMES,
    BeliefDelta,
    ResponsePlanItem,
    ToolCallSpec,
    TurnOutput,
    _extract_json_object,
)

TURN_SCHEMA_NAME_V4 = "turn_output_v4"

# ── Extend V3 schema programmatically ────────────────────────────────────────

from app.routers.v3.schema import TURN_JSON_SCHEMA as _V3_SCHEMA  # noqa: E402

_V4_EXTRA_PROPERTIES: dict = {
    "sub_goals": {
        "type": "array",
        "description": (
            "Ordered list of sub-objectives in this message. Always ≥1 entry. "
            "Multi-intent messages produce ≥2 entries. "
            "args_hint is a JSON-encoded string with intent-relevant arguments."
        ),
        "items": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "search",
                        "scheduling",
                        "knowledge",
                        "negotiation",
                        "rapport",
                        "handoff",
                        "out_of_scope",
                    ],
                    "description": "Intent of this sub-goal",
                },
                "args_hint": {
                    "type": "string",
                    "description": (
                        "JSON-encoded args hint for this sub-goal, e.g. "
                        "'{\"operation\":\"alquiler\",\"tipo\":\"departamento\"}'. "
                        "Use '{}' when no args apply."
                    ),
                },
            },
            "required": ["intent", "args_hint"],
            "additionalProperties": False,
        },
    },
    "references": {
        "type": "object",
        "description": "Anaphora and property-reference resolution for this turn.",
        "properties": {
            "selected_property_id": {
                "type": ["integer", "null"],
                "description": (
                    "Property ID resolved from an anaphoric expression "
                    "('ese', 'el primero', 'ese departamento'), or null."
                ),
            },
            "anaphora": {
                "type": ["string", "null"],
                "description": (
                    "The anaphoric expression the user used, or null. "
                    "E.g. 'ese', 'el primero', 'el de arriba'."
                ),
            },
        },
        "required": ["selected_property_id", "anaphora"],
        "additionalProperties": False,
    },
}

_v3_inner = _V3_SCHEMA["schema"]
_v4_properties = {**_v3_inner["properties"], **_V4_EXTRA_PROPERTIES}
_v4_required = list(_v3_inner["required"]) + ["sub_goals", "references"]

TURN_JSON_SCHEMA_V4: dict = {
    "name": TURN_SCHEMA_NAME_V4,
    "strict": True,
    "schema": {
        "type": "object",
        "properties": _v4_properties,
        "required": _v4_required,
        "additionalProperties": False,
    },
}

RESPONSE_FORMAT_V4: dict = {"type": "json_schema", "json_schema": TURN_JSON_SCHEMA_V4}


# ── Pydantic models ───────────────────────────────────────────────────────────

class SubGoal(BaseModel):
    """A single sub-objective extracted by the V4 perception pass."""

    intent: str
    args_hint: str  # JSON-encoded string; use parsed_args() to decode

    def parsed_args(self) -> dict:
        """Decode args_hint from JSON string to dict. Returns {} on any error."""
        try:
            result = json.loads(self.args_hint)
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}


class References(BaseModel):
    """Anaphora and property-reference resolution fields."""

    selected_property_id: Optional[int] = None
    anaphora: Optional[str] = None


class TurnOutputV4(TurnOutput):
    """V4 engine output: V3 fields + sub_goals + references."""

    sub_goals: list[SubGoal] = []
    references: References = References()


def parse_turn_output_v4(raw: str) -> TurnOutputV4:
    """Parse the LLM's JSON response into a TurnOutputV4.

    Uses raw_decode so trailing text from the model doesn't cause a parse
    failure (same strategy as V3's parse_turn_output — see v3/schema.py).
    Raises ValueError / pydantic.ValidationError on failure.
    """
    data = _extract_json_object(raw)
    if hasattr(TurnOutputV4, "model_validate"):
        return TurnOutputV4.model_validate(data)
    return TurnOutputV4.parse_obj(data)  # pydantic v1
