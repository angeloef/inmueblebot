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

    arguments is a JSON-encoded string (required by OpenAI strict mode).
    Access parsed_args for the decoded dict.
    """
    name: str = Field(..., description="Tool name")
    arguments: str = Field(default="{}", description="Tool arguments as JSON string")

    @property
    def parsed_args(self) -> dict[str, Any]:
        """Decode arguments from JSON string to dict."""
        import json
        try:
            return json.loads(self.arguments)
        except (json.JSONDecodeError, TypeError):
            return {}


class MessageSegment(BaseModel):
    """A single segment in a multi-message response sequence.

    Used when action="respond_with_sequence". Each segment is sent as
    a separate WhatsApp message with a small delay between them.
    """
    type: Literal["text", "images"] = Field(
        default="text",
        description="Segment type: 'text' for a text message, 'images' for images with caption",
    )
    content: Optional[str] = Field(
        default=None,
        description="Text content for 'text' segments, or caption for 'images' segments",
    )
    images: Optional[list[str]] = Field(
        default=None,
        description="Image URLs — only for 'images' segments (max 4)",
    )


class AgentResponse(BaseModel):
    """v2.0 structured LLM response schema.

    Enforced via OpenAI response_format={type: "json_schema", ...}.
    When the LLM calls tools natively, this schema is bypassed.
    When the LLM responds with text, the text MUST parse as this schema.
    """

    action: Literal["tool_call", "respond", "ask_question", "respond_with_sequence"] = Field(
        ...,
        description=(
            "What to do next: "
            "'tool_call' = execute the tool calls listed, "
            "'respond' = deliver the response text as a single message, "
            "'ask_question' = ask the user a question, "
            "'respond_with_sequence' = send multiple sequential messages"
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
    segments: Optional[list[MessageSegment]] = Field(
        default=None,
        description=(
            "Sequential messages to send one by one. "
            "Only when action='respond_with_sequence'. "
            "Example: a warm greeting first, then immediately the next question "
            "as a separate message. Max 4 segments."
        ),
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
                "enum": ["tool_call", "respond", "ask_question", "respond_with_sequence"],
                "description": "What to do next: tool_call, respond, ask_question, or respond_with_sequence",
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
                            "type": "string",
                            "description": "Tool arguments as a JSON-encoded string. Example: '{\"location\": \"Oberá\"}'",
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
            "segments": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["text", "images"],
                            "description": "'text' or 'images'",
                        },
                        "content": {
                            "type": ["string", "null"],
                            "description": "Text content or image caption",
                        },
                        "images": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                            "description": "Image URLs (max 4, for 'images' segments)",
                        },
                    },
                    "required": ["type", "content", "images"],
                    "additionalProperties": False,
                },
                "description": "Sequential message segments for respond_with_sequence.",
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
        "required": [
            "action", "tool_calls", "response", "question", "question_field",
            "segments", "confidence", "reasoning"
        ],
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


# ── ChatbotSerio v2.0 schemas (compatible with S1+S2 router) ──────────────

class MessageChunk(BaseModel):
    """A single message bubble in a multi-message response sequence (CS v2.0)."""
    text: str = Field(..., description="Text content for this message bubble")
    tool_used: str | None = Field(default=None, description="Tool that produced this chunk")
    chunk_type: str = Field(default="tool_result", description="'tool_result' | 'closing'")


class CSAgentResponse(BaseModel):
    """ChatbotSerio's structured agent response — simpler than v1.x AgentResponse."""
    response: str = Field(..., description="Text response to the user")
    tools_called: list[str] = Field(default_factory=list, description="Names of tools invoked")
    raw_tool_results: list[dict[str, Any]] = Field(
        default_factory=list, description="Raw results from tool executions"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Agent confidence (0-1)")
    messages: list[MessageChunk] = Field(default_factory=list, description="Multi-message bubbles")
    belief_corrections: dict[str, Any] = Field(
        default_factory=dict,
        description="Belief-state fields the LLM detected as wrong/missing and corrected "
                    "from the real user message (typos, slang, context). Applied by the router.",
    )


class ChatRequest(BaseModel):
    """Incoming chat request (CS v2.0)."""
    message: str = Field(..., min_length=1, description="User message")
    session_id: str = Field(..., description="Session identifier for multi-turn context")
    phone: str = Field(default="", description="User phone for cross-session memory")


class ChatResponse(BaseModel):
    """Response from the /chat endpoint (CS v2.0)."""
    response: str = Field(..., description="Text response to the user")
    tools_called: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0)
    messages: list[MessageChunk] = Field(default_factory=list)


# ── ChatbotSerio's StructuredToolCall (arguments is dict, not string) ────────

class CSStructuredToolCall(BaseModel):
    """ChatbotSerio's tool call type — arguments is a dict, not a JSON string."""
    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Function name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Parsed arguments")
