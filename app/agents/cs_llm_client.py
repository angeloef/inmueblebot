"""OpenAI-compatible chat completions client wrapper."""

from openai import AsyncOpenAI

from app.core.config import get_settings
settings = get_settings()

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Lazy-init the OpenAI async client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client
