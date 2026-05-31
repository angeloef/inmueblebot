"""LLM client factory — provider-agnostic, OpenAI-compatible interface.

Supported providers (all expose the same OpenAI chat/completions API):
  - openai      (default) — api.openai.com
  - deepseek    — api.deepseek.com  (DeepSeek-V3 = deepseek-chat, R1 = deepseek-reasoner)
  - openrouter  — openrouter.ai/api/v1  (any model via single key)

Select via LLM_PROVIDER env var. Model name via OPENAI_MODEL / DEEPSEEK_MODEL / OPENROUTER_MODEL.
"""

from openai import AsyncOpenAI

from app.core.config import get_settings

_PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
}

_clients: dict[str, AsyncOpenAI] = {}


def get_client() -> AsyncOpenAI:
    """Return the configured LLM client (OpenAI-compatible interface)."""
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()

    if provider not in _clients:
        if provider == "deepseek":
            _clients[provider] = AsyncOpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=_PROVIDER_BASE_URLS["deepseek"],
            )
        elif provider == "openrouter":
            _clients[provider] = AsyncOpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url=_PROVIDER_BASE_URLS["openrouter"],
            )
        else:
            _clients[provider] = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    return _clients[provider]


def get_model() -> str:
    """Return the model ID for the configured provider."""
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()
    if provider == "deepseek":
        return settings.DEEPSEEK_MODEL
    if provider == "openrouter":
        return settings.OPENROUTER_MODEL
    return settings.OPENAI_MODEL


def supports_strict_json_schema() -> bool:
    """Whether the provider supports OpenAI-style strict JSON schema response_format.

    DeepSeek and OpenRouter support json_object but not json_schema with strict=True.
    """
    return get_settings().LLM_PROVIDER.lower() == "openai"
