"""
v2.0 Structured Output Schema.

Every LLM response is either:
- Native OpenAI tool_calls (when the model wants to use a tool)
- A valid AgentResponse JSON (when the model responds with text)

This eliminates the need for regex guards. The action field tells the
orchestrator exactly what to do next.
"""

from __future__ import annotations
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


class StructuredToolCall(BaseModel):
    """A tool call within a structured AgentResponse.

    Used when action="tool_call" and the model describes tools inline
    rather than using OpenAI's native tool_calls mechanism.
    """
    name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class AgentResponse(BaseModel):
    """v2.0 structured LLM response schema.

    Enforced via OpenAI response_format={type: "json_schema", ...}.
    When the LLM calls tools natively, this schema is bypassed.
    When the LLM responds with text, the text MUST parse as this schema.
    """

    action: Literal["tool_call", "respond", "ask_question"] = Field(
        ...,
        description=(
            "What to do next: "
            "'tool_call' = execute the tool calls listed, "
            "'respond' = deliver the response text, "
            "'ask_question' = ask the user a question"
        ),
    )
    tool_calls: list[StructuredToolCall] = Field(
        default_factory=list,
        description="Tools to execute when action='tool_call'. Empty otherwise.",
    )
    response: Optional[str] = Field(
        default=None,
        description="Final user-facing response text. Only when action='respond'.",
    )
    question: Optional[str] = Field(
        default=None,
        description="Question to ask the user. Only when action='ask_question'.",
    )
    question_field: Optional[Literal["date", "time", "name", "generic"]] = Field(
        default=None,
        description="What information the question is asking for.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Self-reported confidence (0-1). Used for progressive escalation.",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief reasoning for debugging. Not shown to user.",
    )


# ── OpenAI JSON Schema for response_format ────────────────────────────────

AGENT_RESPONSE_JSON_SCHEMA = {
    "name": "agent_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["tool_call", "respond", "ask_question"],
                "description": "What to do next: tool_call, respond, or ask_question",
            },
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Tool name",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Tool arguments",
                        },
                    },
                    "required": ["name", "arguments"],
                    "additionalProperties": False,
                },
                "description": "Tools to execute. Only when action='tool_call'.",
            },
            "response": {
                "type": ["string", "null"],
                "description": "Final user-facing response. Only when action='respond'.",
            },
            "question": {
                "type": ["string", "null"],
                "description": "Question to ask the user. Only when action='ask_question'.",
            },
            "question_field": {
                "type": ["string", "null"],
                "enum": ["date", "time", "name", "generic", None],
                "description": "What the question is asking for.",
            },
            "confidence": {
                "type": "number",
                "description": "Self-reported confidence 0.0-1.0",
            },
            "reasoning": {
                "type": ["string", "null"],
                "description": "Brief reasoning for debugging.",
            },
        },
        "required": ["action", "tool_calls", "confidence"],
        "additionalProperties": False,
    },
}


# ── Safe fallback responses ──────────────────────────────────────────────

FALLBACK_RESPONSE = AgentResponse(
    action="respond",
    response="Disculpá, tuve un problema técnico. ¿Podrías repetirme lo que necesitás?",
    confidence=0.0,
    reasoning="Structured output parsing failed — fallback response",
)

OUT_OF_SCOPE_RESPONSE = AgentResponse(
    action="respond",
    response=(
        "Soy la asistente de la inmobiliaria y solo puedo ayudarte con "
        "propiedades, alquileres y visitas. ¿Hay algo en ese sentido "
        "en lo que pueda ayudarte?"
    ),
    confidence=0.95,
    reasoning="Out of scope detected",
)
