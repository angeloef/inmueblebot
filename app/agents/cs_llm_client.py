"""LLM client factory with role-aware model selection. OpenAI only.

Supported roles:
  - REASONING  — gpt-5.5 — tool decisions, agent loop
  - CLASSIFY   — gpt-5.4-mini — intent classification
  - SYNTH      — gpt-5.4-mini — final text synthesis
  - DEFAULT    — fallback, uses OPENAI_MODEL

Model tiering is enabled via LLM_TIERING_ENABLED=true in config.
When disabled (default), all roles use OPENAI_MODEL.
"""

from enum import Enum
from typing import Optional
from openai import AsyncOpenAI

from app.core.config import get_settings


class LLMRole(str, Enum):
    REASONING = "reasoning"  # gpt-5.5 — tool decisions, agent loop
    CLASSIFY = "classify"    # gpt-5.4-mini — intent classification
    SYNTH = "synth"          # gpt-5.4-mini — final text synthesis
    DEFAULT = "default"      # fallback, uses OPENAI_MODEL


_client: Optional[AsyncOpenAI] = None


def get_client(role: LLMRole = LLMRole.DEFAULT) -> AsyncOpenAI:
    """Returns an AsyncOpenAI client. All roles use the same OpenAI endpoint."""
    global _client
    settings = get_settings()
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
    return _client


def get_model(role: LLMRole = LLMRole.DEFAULT) -> str:
    """Returns the correct model ID for the given role.

    When LLM_TIERING_ENABLED is False (default), always returns OPENAI_MODEL
    regardless of role — preserving existing behavior.

    When tiering is enabled:
    - REASONING → LLM_MODEL_REASONING or OPENAI_MODEL_REASONING (gpt-5.5)
    - CLASSIFY/SYNTH → LLM_MODEL_CLASSIFY or OPENAI_MODEL_FAST (gpt-5.4-mini)
    - DEFAULT → OPENAI_MODEL
    """
    settings = get_settings()

    # If tiering is disabled, always return the default model
    if not getattr(settings, "LLM_TIERING_ENABLED", False):
        return getattr(settings, "OPENAI_MODEL", "gpt-5.4-mini")

    # Role-specific model selection
    if role == LLMRole.REASONING:
        return (
            getattr(settings, "LLM_MODEL_REASONING", None)
            or getattr(settings, "OPENAI_MODEL_REASONING", "gpt-5.5")
        )
    elif role in (LLMRole.CLASSIFY, LLMRole.SYNTH):
        return (
            getattr(settings, "LLM_MODEL_CLASSIFY", None)
            or getattr(settings, "OPENAI_MODEL_FAST", "gpt-5.4-mini")
        )
    else:
        return getattr(settings, "OPENAI_MODEL", "gpt-5.4-mini")


def supports_strict_json_schema(role: LLMRole = LLMRole.DEFAULT) -> bool:
    """OpenAI always supports strict JSON schema."""
    return True


def max_tokens_kwarg(n: int, role: LLMRole = LLMRole.DEFAULT) -> dict:
    """Returns the correct token-limit kwarg for the model.

    GPT-5 and o-series models require max_completion_tokens.
    Older models (gpt-4*, gpt-3.5*) use max_tokens.
    """
    model = get_model(role)
    if model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4"):
        return {"max_completion_tokens": n}
    return {"max_tokens": n}
