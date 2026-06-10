"""V3 engine output schema — hand-built strict JSON schema + thin Pydantic layer.

OpenAI strict-mode rules enforced throughout:
- Every object has additionalProperties:false
- Every property key is in required
- Optional/nullable via ["type","null"] union
- Enums allowing null include null in the enum list AND use ["string","null"] type
- tool_calls[].arguments is a JSON-encoded string (engine json.loads it)
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

# ── Tool names (verified against TOOL_REGISTRY.keys() in app/tools/v2/registry.py) ──
# echo/get_time were reachable by the model but have no real-estate purpose and only
# invited off-task tool calls — dropped from the V3 enum (plan #20). They remain in the
# registry for legacy callers; the V3 engine simply never offers them.
_TOOL_NAMES = [
    "search_properties",
    "get_property_details",
    "get_property_images",
    "get_faq_answer",
    "schedule_visit",
    "get_my_appointments",
    "cancel_appointment",
    "reschedule_appointment",
    "request_human_assistance",
]

TURN_SCHEMA_NAME = "turn_output"

# Hand-built strict JSON schema — mirrors the structure of AGENT_RESPONSE_JSON_SCHEMA
# in app/agents/schemas.py but for V3's richer output contract.
TURN_JSON_SCHEMA: dict = {
    "name": TURN_SCHEMA_NAME,
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "belief_delta": {
                "type": "object",
                "description": (
                    "Fields extracted from this turn that update the conversation belief. "
                    "Only include what the user expressed THIS turn. Null = not mentioned."
                ),
                "properties": {
                    "operation": {
                        "type": ["string", "null"],
                        "enum": ["alquiler", "venta", None],
                        "description": "'alquiler' | 'venta' | null",
                    },
                    "property_type": {
                        "type": ["string", "null"],
                        "enum": ["departamento", "casa", "ph", "terreno", None],
                        "description": "Canonical property type or null",
                    },
                    "zone": {
                        "type": ["string", "null"],
                        "description": "Neighborhood/zone string or null",
                    },
                    "budget_max": {
                        "type": ["number", "null"],
                        "description": "Max budget in ARS or null",
                    },
                    "bedrooms_min": {
                        "type": ["integer", "null"],
                        "description": "Min bedrooms or null",
                    },
                },
                "required": ["operation", "property_type", "zone", "budget_max", "bedrooms_min"],
                "additionalProperties": False,
            },
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
                "description": "Primary intent classification for this turn",
            },
            "action": {
                "type": "string",
                "enum": [
                    "search",
                    "show_details",
                    "show_photos",
                    "answer_knowledge",
                    "book_step",
                    "clarify",
                    "handoff",
                    "smalltalk",
                ],
                "description": "Concrete action the engine should take",
            },
            "tool_calls": {
                "type": "array",
                "description": "Ordered list of tools to execute deterministically",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": _TOOL_NAMES,
                            "description": "Tool name from the registry",
                        },
                        "arguments": {
                            "type": "string",
                            "description": "Tool arguments as a JSON-encoded string, e.g. '{\"property_id\": 7}'",
                        },
                    },
                    "required": ["name", "arguments"],
                    "additionalProperties": False,
                },
            },
            "selected_property_id": {
                "type": ["integer", "null"],
                "description": "Property ID the user is now focused on, or null",
            },
            "missing_slot": {
                "type": ["string", "null"],
                "enum": ["scheduling_day", "scheduling_time", "scheduling_name", None],
                "description": "First missing scheduling slot to ask for, or null",
            },
            "response_plan": {
                "type": "array",
                "description": "Ordered message segments to send to the user",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["text", "images"],
                            "description": "'text' for a text message, 'images' for a photo segment",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content or image caption",
                        },
                    },
                    "required": ["type", "content"],
                    "additionalProperties": False,
                },
            },
            "confidence": {
                "type": "number",
                "description": "Self-reported confidence 0.0–1.0",
            },
        },
        "required": [
            "belief_delta",
            "intent",
            "action",
            "tool_calls",
            "selected_property_id",
            "missing_slot",
            "response_plan",
            "confidence",
        ],
        "additionalProperties": False,
    },
}

RESPONSE_FORMAT: dict = {"type": "json_schema", "json_schema": TURN_JSON_SCHEMA}


# ── Pydantic models for typed parsing ─────────────────────────────────────────

class BeliefDelta(BaseModel):
    """Extracted belief updates from a single turn."""
    operation: Optional[str] = None
    property_type: Optional[str] = None
    zone: Optional[str] = None
    budget_max: Optional[float] = None
    bedrooms_min: Optional[int] = None


class ToolCallSpec(BaseModel):
    """A single tool call specification from the engine output."""
    name: str
    arguments: str  # JSON-encoded string; use parsed_args() to decode

    def parsed_args(self) -> dict:
        """Decode arguments from JSON string to dict. Returns {} on any error."""
        try:
            result = json.loads(self.arguments)
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}


class ResponsePlanItem(BaseModel):
    """A single segment in the response plan."""
    type: str   # "text" | "images"
    content: str


class TurnOutput(BaseModel):
    """Parsed output from the V3 engine LLM call."""
    belief_delta: BeliefDelta
    intent: str
    action: str
    tool_calls: list[ToolCallSpec]
    selected_property_id: Optional[int] = None
    missing_slot: Optional[str] = None
    response_plan: list[ResponsePlanItem]
    confidence: float


def _extract_json_object(raw: str) -> dict:
    """Extract the first JSON object from an LLM response.

    Strict structured outputs *should* return a bare JSON object, but in
    practice the engine model (gpt-5.4-mini) sometimes appends trailing text on
    a second line or wraps the object in ```json fences. A plain json.loads()
    then fails with "Extra data: line 2 column 1", the whole turn is discarded,
    and the caller falls back to a low-confidence regex clarify — re-asking what
    the user already answered. Decoding only the first object tolerates that
    noise while keeping the structured slots.
    """
    text = raw.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.lstrip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in engine output")
    # raw_decode parses the first complete object and ignores any trailing data.
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("engine output is not a JSON object")
    return obj


def parse_turn_output(raw: str) -> TurnOutput:
    """Parse the LLM's JSON string response into a TurnOutput.

    Raises ValueError / pydantic.ValidationError on failure.
    The caller must catch and trigger the fallback path.
    """
    data = _extract_json_object(raw)
    # Supports both pydantic v1 (.parse_obj) and v2 (.model_validate)
    if hasattr(TurnOutput, "model_validate"):
        return TurnOutput.model_validate(data)
    return TurnOutput.parse_obj(data)  # pydantic v1
